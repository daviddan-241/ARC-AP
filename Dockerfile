# ArenaOS — Render free-tier optimized image.
# Free tier = 512MB RAM. Choices below keep the BASE footprint small;
# headless Chromium is only LAUNCHED lazily on the first model call, so idle RAM stays low.
# If RAM proves too tight on free tier, bump to Render's $7 Starter (no code change needed).

FROM python:3.11-slim

# 1 = install headless Chromium for the arena.ai web-session transport (default).
# Set to 0 for a much lighter image when using the formal Arena API adapter instead.
ARG ARENA_BROWSER=1
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

# Real power-user toolset baked into the image — no root needed at runtime to use
# any of these. apt itself still requires root by design (the app runs as the
# non-root `arenaos` user below), so packages.install only covers pip/npm at
# runtime; see arenaos/tools/packages.py. Categories: version control + net
# fetch, network diagnostics, archives, media/image editing, data tools, OCR,
# and Node/build toolchains so packages.install's npm path actually works.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl wget ca-certificates openssl \
    dnsutils whois netcat-openbsd nmap iputils-ping \
    zip unzip jq sqlite3 \
    ffmpeg imagemagick tesseract-ocr \
    build-essential python3-venv \
    nodejs npm \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/arenaos
COPY pyproject.toml README.md ./
COPY arenaos ./arenaos
COPY ui-react/dist ./ui-react/dist
COPY plugins ./plugins
COPY tests ./tests
RUN pip install --no-cache-dir '.[postgres]'

# REAL BUG THIS FIXES: playwright install used to run here as root (the
# default user at this point in the build), which writes browsers to
# /root/.cache/ms-playwright. The app runs at RUNTIME as the non-root
# `arenaos` user (HOME=/home/arenaos), so Playwright looked in
# /home/arenaos/.cache/ms-playwright and found nothing — every browser
# launch crashed with "Executable doesn't exist at
# /home/arenaos/.cache/ms-playwright/...". Fix: pin PLAYWRIGHT_BROWSERS_PATH
# to one fixed, user-independent directory that's both installed into at
# build time and read from at runtime — no dependency on whose $HOME it is.
ENV PLAYWRIGHT_BROWSERS_PATH=/srv/arenaos/pw-browsers
RUN if [ "$ARENA_BROWSER" = "1" ]; then \
        apt-get update && apt-get install -y --no-install-recommends \
            libnspr4 libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
            libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
            libgbm1 libasound2 libpango-1.0-0 libcairo2 fonts-liberation \
        && apt-get clean && rm -rf /var/lib/apt/lists/* \
        && pip install --no-cache-dir '.[browser]' \
        && (python -m playwright install --with-deps chromium || python -m playwright install chromium); \
    fi

# Non-root user; the browser profile dir AND the pinned playwright browsers
# dir must both be writable/readable by arenaos (see PLAYWRIGHT_BROWSERS_PATH
# above — this chown is what actually makes the fix work end to end).
RUN useradd -m arenaos && mkdir -p /srv/arenaos/data && \
    chown -R arenaos:arenaos /srv/arenaos
USER arenaos

ENV DATA_DIR=/srv/arenaos/data
EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

# Single worker, no access logs: minimum RAM on the free tier.
CMD ["uvicorn", "arenaos.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
