#!/usr/bin/env python3
"""Private, dependency-free Ashframe game-control dashboard."""
from __future__ import annotations

import html
import os
import re
import secrets
import subprocess
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

LISTEN_ADDRESSES = tuple(os.environ.get("ASHFRAME_DASHBOARD_LISTEN", "127.0.0.1").split(","))
PORT = int(os.environ.get("ASHFRAME_DASHBOARD_PORT", "9080"))
GAME_ROOT = Path(os.environ.get("ASHFRAME_GAME_ROOT", str(Path.home() / "games")))
BACKUP_ROOT = Path(os.environ.get("ASHFRAME_GAME_DATA_ROOT", str(Path.home() / ".local/share/ashframe-game-control"))) / "backups"
CSRF_TOKEN_FILE = BACKUP_ROOT.parent / "dashboard-csrf-token"


def load_csrf_token() -> str:
    """Keep the token across a service restart, without placing it in the repo."""
    try:
        token = CSRF_TOKEN_FILE.read_text(encoding="utf-8").strip()
        if token:
            return token
    except FileNotFoundError:
        pass
    CSRF_TOKEN_FILE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    descriptor = os.open(CSRF_TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        file.write(token + "\n")
    return token


CSRF_TOKEN = load_csrf_token()
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
COMMAND_HISTORY: dict[str, list[str]] = {}


def config(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def command(*args: str) -> str:
    result = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    return result.stdout.strip()


def service_state(game_id: str) -> str:
    return command("systemctl", "is-active", f"ashframe-{game_id}.service") or "unknown"


def console_output(game_id: str) -> str:
    logs = command("journalctl", "-u", f"ashframe-{game_id}.service", "-n", "120", "--no-pager") or "No service logs yet."
    history = COMMAND_HISTORY.get(game_id, [])
    if history:
        return logs + "\n\n// DASHBOARD COMMAND HISTORY\n" + "\n".join(history)
    return logs


def service_enabled(game_id: str) -> bool:
    return subprocess.run(["systemctl", "is-enabled", "--quiet", f"ashframe-{game_id}.service"], check=False).returncode == 0


def next_timer(unit: str) -> str:
    value = command("systemctl", "show", unit, "-p", "NextElapseUSecRealtime", "--value")
    return value or "Not scheduled"


def hytale_next(root: Path, game: dict[str, str]) -> str:
    directory = root / game.get("NATIVE_BACKUP_PATH", "")
    candidates = list(directory.glob("*.zip"))
    if not candidates:
        return "After the server starts"
    newest = max(candidates, key=lambda item: item.stat().st_mtime)
    estimate = datetime.fromtimestamp(newest.stat().st_mtime) + timedelta(hours=8)
    return estimate.strftime("%a %d %b, %H:%M") + " (estimated)"


def latest_backup(root: Path, game: dict[str, str]) -> tuple[str, str]:
    if game.get("GAME_TYPE") == "hytale":
        directory = root / game.get("NATIVE_BACKUP_PATH", "")
        candidates = list(directory.glob("*.zip"))
    else:
        directory = BACKUP_ROOT / game.get("BACKUP_PATH", game["GAME_ID"])
        candidates = list(directory.glob("*.tar.zst"))
    if not candidates:
        return "None yet", ""
    newest = max(candidates, key=lambda item: item.stat().st_mtime)
    modified = datetime.fromtimestamp(newest.stat().st_mtime).strftime("%d %b %Y, %H:%M")
    size = newest.stat().st_size / 1024 / 1024
    return modified, f"{size:.0f} MiB"


def games() -> list[tuple[Path, dict[str, str]]]:
    found: list[tuple[Path, dict[str, str]]] = []
    for file in sorted(GAME_ROOT.glob("*/.ashframe-game.conf")):
        values = config(file)
        if SAFE_ID.fullmatch(values.get("GAME_ID", "")) and values.get("ENABLED") == "true":
            found.append((file.parent, values))
    return found


def page(title: str, body: str, notice: str = "") -> bytes:
    notice_html = f'<p class="notice">{html.escape(notice)}</p>' if notice else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} — Ashframe</title><link rel="stylesheet" href="/static/dashboard.css"></head>
<body><header><a class="brand" href="/"><span class="mark">A</span> ASHFRAME</a><span>PRIVATE GAME CONTROL</span></header>
<main>{notice_html}{body}</main><footer><span>ASHFRAME © 2026</span><span>HOME SERVER · PRIVATE ACCESS</span></footer></body></html>""".encode()


def action_form(game_id: str, action: str, label: str) -> str:
    return f'''<form method="post" action="/action"><input type="hidden" name="csrf" value="{CSRF_TOKEN}"><input type="hidden" name="game" value="{html.escape(game_id)}"><input type="hidden" name="action" value="{action}"><button>{label}</button></form>'''


def console_fifo(game_id: str) -> Path:
    return Path(f"/run/ashframe-game-{game_id}/console.in")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        return

    def send_page(self, content: bytes, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def send_text(self, content: str, status: int = 200) -> None:
        encoded = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        query = parse_qs(urlparse(self.path).query)
        if path == "/static/dashboard.css":
            css = (Path(__file__).parent / "static/dashboard.css").read_bytes()
            self.send_response(200); self.send_header("Content-Type", "text/css; charset=utf-8"); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(css)
            return
        if path == "/console-output":
            game_id = query.get("game", [""])[0]
            if not SAFE_ID.fullmatch(game_id):
                self.send_text("Unknown game.\n", 404); return
            self.send_text(console_output(game_id) + "\n")
            return
        if path == "/logs":
            game_id = query.get("game", [""])[0]
            if not SAFE_ID.fullmatch(game_id):
                self.send_page(page("Not found", "<h1>Unknown game.</h1>"), 404); return
            logs = console_output(game_id)
            fifo = console_fifo(game_id)
            if fifo.exists():
                console = f'''<form id="console-form" method="post" action="/console"><input type="hidden" name="csrf" value="{CSRF_TOKEN}"><input type="hidden" name="game" value="{html.escape(game_id)}">'''
            else:
                console = '<p class="migration">Console becomes available after this service has been restarted with the updated manager.</p>'
            terminal_input = '''<div class="terminal-input"><span>›</span><input id="line" name="line" maxlength="500" autocomplete="off" placeholder="Type a server command" autofocus><button>Send</button></div>''' if fifo.exists() else ""
            close_form = "</form>" if fifo.exists() else ""
            body = f'''<style>.terminal{{border:1px solid #303030;background:#0c0c0c}}.terminal pre{{border:0;margin:0;min-height:360px;max-height:62vh;padding:20px;overflow:auto}}.terminal-input{{border-top:1px solid #303030;display:flex;align-items:center;padding:0 14px;color:#f0322e}}.terminal-input input{{flex:1;min-width:0;border:0;outline:0;background:transparent;color:#ececec;font:14px ui-monospace,monospace;padding:16px 12px}}.terminal-input button{{border:0;border-left:1px solid #303030;padding:16px}}.console-status{{min-height:1.3em;margin:8px 0 0;color:#aaa;font:12px ui-monospace,monospace}}.console-status.error{{color:#f0322e}}</style><a class="back" href="/">← Back to overview</a><p class="eyebrow">// LIVE SERVICE CONSOLE</p><h1>{html.escape(game_id)}.</h1>{console}<div class="terminal"><pre id="console-output">{html.escape(logs)}</pre>{terminal_input}</div><p id="console-status" class="console-status" aria-live="polite"></p>{close_form}<script>
const output = document.getElementById("console-output");
const status = document.getElementById("console-status");
async function refreshConsole() {{
  const atBottom = output.scrollHeight - output.scrollTop - output.clientHeight < 40;
  try {{ const response = await fetch("/console-output?game={html.escape(game_id)}", {{cache: "no-store", credentials: "same-origin"}}); if (response.ok) {{ output.textContent = await response.text(); if (atBottom) output.scrollTop = output.scrollHeight; }} }} catch (_) {{}}
}}
setInterval(refreshConsole, 3000);
const form = document.getElementById("console-form");
if (form) {{
  const input = document.getElementById("line");
  form.addEventListener("submit", async (event) => {{
    event.preventDefault();
    const line = input.value.trim();
    if (!line) return;
    status.className = "console-status"; status.textContent = "Sending command…";
    try {{
      // Build the request explicitly. This avoids relying on browser form
      // serialisation for the hidden game field in a live-updating terminal.
      const body = new URLSearchParams({{game: "{html.escape(game_id)}", line}});
      const response = await fetch("/console", {{method: "POST", body, cache: "no-store", credentials: "same-origin"}});
      if (!response.ok) {{ status.className = "console-status error"; status.textContent = `Command rejected (${{response.status}}). Reload the page once and try again.`; return; }}
      output.textContent = await response.text();
      output.scrollTop = output.scrollHeight;
      input.value = ""; input.focus();
      status.textContent = "Command sent.";
      setTimeout(refreshConsole, 350);
    }} catch (_) {{ status.className = "console-status error"; status.textContent = "Console send failed."; }}
  }});
}}
</script>'''
            self.send_page(page("Console", body, query.get("notice", [""])[0]))
            return
        if path != "/":
            self.send_page(page("Not found", "<h1>Not found.</h1>"), 404); return
        cards = []
        for root, game in games():
            game_id = game["GAME_ID"]
            state = service_state(game_id)
            enabled = service_enabled(game_id)
            last, size = latest_backup(root, game)
            controls = f'<div class="actions">{action_form(game_id, "start", "Start")}{action_form(game_id, "restart", "Restart")}{action_form(game_id, "stop", "Stop")}</div>' if enabled else '<p class="migration">Enable its service to manage it here.</p>'
            cards.append(f'''<article class="game"><div class="game-top"><span class="number">{html.escape(game.get("GAME_TYPE", "GAME").upper())}</span><span class="state {html.escape(state)}">● {html.escape(state)}</span></div><h2>{html.escape(game.get("DISPLAY_NAME", game_id))}.</h2><dl><div><dt>LAST LOCAL BACKUP</dt><dd>{html.escape(last)}</dd></div><div><dt>ARCHIVE SIZE</dt><dd>{html.escape(size or "—")}</dd></div><div><dt>BACKUP MODE</dt><dd>{html.escape(game.get("BACKUP_MODE", "—"))}</dd></div></dl>{controls}<a class="logs" href="/logs?game={html.escape(game_id)}">Open console ↗</a></article>''')
        hytale = next((game for root, game in games() if game.get("GAME_ID") == "hytale"), None)
        hytale_root = next((root for root, game in games() if game.get("GAME_ID") == "hytale"), None)
        native_next = hytale_next(hytale_root, hytale) if hytale and hytale_root else "Not configured"
        body = f'''<section class="hero"><p class="eyebrow">// ASHFRAME HOME SERVER</p><h1>GAME<br><em>CONTROL.</em></h1><p>Private service and backup overview. Accessible only through local access or an SSH tunnel.</p></section><section class="section-title"><span>// REGISTERED GAMES</span><span>{len(cards)} LISTED</span></section><section class="grid">{''.join(cards) or '<p>No game configurations found.</p>'}</section><section class="schedule"><p class="eyebrow">// AUTOMATION</p><dl><div><dt>NEXT CUBYZ SNAPSHOT</dt><dd>{html.escape(next_timer("ashframe-game-snapshot.timer"))}</dd></div><div><dt>NEXT VPS UPLOAD</dt><dd>{html.escape(next_timer("ashframe-game-upload.timer"))}</dd></div><div><dt>HYTALE NATIVE BACKUP</dt><dd>{html.escape(native_next)}</dd></div></dl></section>'''
        self.send_page(page("Game Control", body, query.get("notice", [""])[0]))

    def do_POST(self) -> None:
        endpoint = urlparse(self.path).path
        if endpoint not in {"/action", "/console"}:
            self.send_page(page("Not found", "<h1>Not found.</h1>"), 404); return
        length = int(self.headers.get("Content-Length", "0"))
        data = parse_qs(self.rfile.read(length).decode("utf-8"))
        game_id, action, token = data.get("game", [""])[0], data.get("action", [""])[0], data.get("csrf", [""])[0]
        # Authentication is handled by Caddy before a request reaches this
        # private service. Keep the application layer deliberately simple.
        if not SAFE_ID.fullmatch(game_id) or (endpoint == "/action" and action not in {"start", "stop", "restart"}):
            self.send_page(page("Denied", "<h1>Request denied.</h1>"), 403); return
        known = {game["GAME_ID"] for _, game in games()}
        if game_id not in known:
            self.send_page(page("Denied", "<h1>Unknown game.</h1>"), 404); return
        if endpoint == "/console":
            line = data.get("line", [""])[0].strip()
            if not line or "\n" in line or "\r" in line or len(line) > 500:
                self.send_page(page("Denied", "<h1>Invalid console command.</h1>"), 400); return
            fifo = console_fifo(game_id)
            try:
                descriptor = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
                with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                    stream.write(line + "\n")
            except OSError:
                self.send_response(303); self.send_header("Location", f"/logs?game={game_id}&notice=Console%20is%20not%20available."); self.end_headers(); return
            timestamp = datetime.now().strftime("%H:%M:%S")
            COMMAND_HISTORY.setdefault(game_id, []).append(f"[{timestamp}] > {line}")
            COMMAND_HISTORY[game_id] = COMMAND_HISTORY[game_id][-100:]
            self.send_text(console_output(game_id) + "\n"); return
        command("sudo", "/usr/local/sbin/ashframe-game-action", action, game_id)
        self.send_response(303); self.send_header("Location", f"/?notice=Requested%20{action}%20for%20{game_id}."); self.end_headers()


servers = [ThreadingHTTPServer((address, PORT), Handler) for address in LISTEN_ADDRESSES]
for server in servers[1:]:
    threading.Thread(target=server.serve_forever, daemon=True).start()
servers[0].serve_forever()
