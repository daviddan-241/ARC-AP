# ArenaOS — Render free-tier optimized image.
# Free tier = 512MB RAM. Choices below keep the BASE footprint small;
# headless Chromium is only LAUNCHED lazily on the first model call, so idle RAM stays low.
# If RAM proves too tight on free tier, bump to Render's $7 Starter (no code change needed).

FROM python:3.11-slim

# 1 = install headless Chromium for the arena.ai web-session transport (default).
# Set to 0 for a much lighter image when using the formal Arena API adapter instead.
ARG ARENA_BROWSER=1
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/arenaos
COPY pyproject.toml README.md ./
COPY arenaos ./arenaos
COPY plugins ./plugins
COPY tests ./tests
RUN pip install --no-cache-dir '.[postgres]'

RUN if [ "$ARENA_BROWSER" = "1" ]; then \
        apt-get update && apt-get install -y --no-install-recommends \
            libnspr4 libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
            libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
            libgbm1 libasound2 libpango-1.0-0 libcairo2 fonts-liberation \
        && rm -rf /var/lib/apt/lists/* \
        && pip install --no-cache-dir '.[browser]' \
        && python -m playwright install chromium; \
    fi

# Non-root user; the browser profile dir must be writable.
RUN useradd -m arenaos && mkdir -p /srv/arenaos/data && chown -R arenaos:arenaos /srv/arenaos
USER arenaos

ENV DATA_DIR=/srv/arenaos/data
EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

# Single worker, no access logs: minimum RAM on the free tier.
CMD ["uvicorn", "arenaos.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
