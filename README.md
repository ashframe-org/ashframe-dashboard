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

## License and branding

The code is released under the MIT License. “Ashframe”, its logos, and its visual identity are not licensed for reuse or endorsement. See `LICENSE`.
