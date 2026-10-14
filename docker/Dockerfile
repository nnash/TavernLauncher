# Runs the headless TavernLauncher server + the Windows game exe under Wine.
# The launcher source and the game install are NOT baked in: mount them
# (see docker-compose.yml).
FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    WINEPREFIX=/wine \
    WINEARCH=win64 \
    WINEDEBUG=-all \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        wine wine64 xvfb xauth python3 ca-certificates tini \
    && rm -rf /var/lib/apt/lists/*

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

WORKDIR /launcher
EXPOSE 1757-1762/tcp 1757-1762/udp
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]
