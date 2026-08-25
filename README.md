# Ashframe Dashboard

A small, dependency-free dashboard and backup foundation for self-hosted game servers. It was built for Ashframe's home infrastructure, then published as a generic reference implementation.

It does not modify game-server code. Each server has a local `.ashframe-game.conf` describing its launch command, world path, and archive destination.

## Features

- Start, stop, restart, and view logs for configured systemd game services.
- Send a single line to a game's standard input through a narrow FIFO.
- Cubyz safe-copy archives using Zstandard.
- Hytale native-backup retention and off-site copy support.
- Minecraft RCON `save-all flush` adapter.
- SHA-256 integrity checks and checksum-based upload skipping.
- Project/server archive paths such as `cubyz/season-3` and `hytale/vanilla`.

## Before using it

This repository intentionally contains **no** passwords, SSH keys, IP addresses, domains, real server paths, or off-site destinations. Review the scripts before deploying them. It is a framework, not a one-command installer.

Set these environment variables in your own systemd units or shell profile:

```text
ASHFRAME_GAME_ROOT=/srv/games
ASHFRAME_GAME_DATA_ROOT=/var/lib/ashframe-game-control
ASHFRAME_BACKUP_SFTP_TARGET=backup-host
ASHFRAME_BACKUP_SFTP_KEY=/etc/ashframe-game-control/backup_ed25519
ASHFRAME_DASHBOARD_LISTEN=127.0.0.1
ASHFRAME_DASHBOARD_PORT=9080
```

Keep the dashboard private. Put it behind your own reverse-proxy authentication or access it only over a VPN/SSH tunnel. Do not expose it directly to the internet.

## Configuration

Copy a file from `configs/` into the relevant server directory as `.ashframe-game.conf`, then replace every example value. The important field for preventing servers from mixing their backups is:

```text
BACKUP_PATH=hytale/vanilla
```

Every server must use a unique two-segment `project/server` value. Native Hytale archives remain inside that server's own installation; managed local and off-site archives use `BACKUP_PATH`.

## Commands

Once installed into a location of your choosing:

```bash
ashframe-game list
ashframe-game status hytale-example
ashframe-game backup cubyz-example
ashframe-game upload cubyz-example
```

The dashboard is `dashboard/dashboard.py`; it only depends on Python's standard library. The accompanying CSS is deliberately simple and can be replaced.

## License and branding

The code is released under the MIT License. “Ashframe”, its logos, and its visual identity are not licensed for reuse or endorsement. See `LICENSE`.
