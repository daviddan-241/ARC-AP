FROM python:3.12-slim

# Real Linux tooling for the ARC terminal + headless browser screenshots
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash curl wget git jq sqlite3 ca-certificates chromium ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static

RUN mkdir -p /workspace/projects /workspace/files /workspace/tools /workspace/tmp /workspace/output
ENV ARC_DATA_DIR=/workspace

EXPOSE 8000
ENV PORT=8000
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
