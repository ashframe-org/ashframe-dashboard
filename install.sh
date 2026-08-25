#!/usr/bin/env bash
# Run as root on the home server. It installs control tools and timers only;
# game services remain disabled until you deliberately switch them over.
set -euo pipefail

root="$(cd "$(dirname "$0")" && pwd)"
install -d -o root -g root -m 0755 /opt/ashframe-game-control
install -o root -g root -m 0755 "$root/ashframe-game" /opt/ashframe-game-control/ashframe-game
install -o root -g root -m 0755 "$root/ashframe-game-backup" /opt/ashframe-game-control/ashframe-game-backup
install -o root -g root -m 0755 "$root/ashframe-game-service" /opt/ashframe-game-control/ashframe-game-service
install -d -o root -g root -m 0755 /opt/ashframe-game-control/templates
install -o root -g root -m 0644 "$root/templates/minecraft-game.conf.example" /opt/ashframe-game-control/templates/minecraft-game.conf.example
ln -sfn /opt/ashframe-game-control/ashframe-game /usr/local/bin/ashframe-game
install -d -o root -g root -m 0755 /opt/ashframe-game-control/dashboard/static
install -o root -g root -m 0755 "$root/dashboard/dashboard.py" /opt/ashframe-game-control/dashboard/dashboard.py
install -o root -g root -m 0755 "$root/dashboard/ashframe-game-action" /usr/local/sbin/ashframe-game-action
install -o root -g root -m 0644 "$root/dashboard/static/dashboard.css" /opt/ashframe-game-control/dashboard/static/dashboard.css
install -o root -g root -m 0644 "$root/dashboard/systemd/ashframe-game-dashboard.service" /etc/systemd/system/ashframe-game-dashboard.service
install -o root -g root -m 0440 "$root/dashboard/ashframe-game-dashboard.sudoers" /etc/sudoers.d/ashframe-game-dashboard
visudo -cf /etc/sudoers.d/ashframe-game-dashboard
systemctl daemon-reload
systemctl enable --now ashframe-game-dashboard.service

echo 'Installed the dashboard tools. Create your own per-game systemd services and timers.'
