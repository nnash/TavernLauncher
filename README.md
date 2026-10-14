# TavernLauncher
Launchers for client/server management of A Township Tale

## Docker (headless server)

Runs the server launcher with no GUI, and the game exe under Wine. The launcher
source and game install are mounted, not baked in.

```
cd docker
GAME_DIR=/path/to/"A Township Tale" docker compose up -d --build
```

- Config: `tavern_server.json` / `server_settings.json` live in the `tavern-wine` volume
  (`/wine/drive_c/users/root/AppData/Roaming/TheModdingTavern`), or use the
  `TAVERN_SERVER_EXE` / `TAVERN_SERVER_PORT` env vars in the compose file.
- `docker kill -s HUP <container>` reboots the game server; `docker stop` shuts it down cleanly.
- Ports 1757–1762 (TCP+UDP). Game logs appear in `docker logs`.
