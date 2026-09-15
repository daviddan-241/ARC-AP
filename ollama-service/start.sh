#!/bin/sh
# ARC model host — pulls models (comma list from OLLAMA_MODELS) then serves.
set -e
export OLLAMA_HOST="0.0.0.0:${PORT:-11434}"

ollama serve &
SERVER_PID=$!

# wait for the server socket
i=0
while [ $i -lt 60 ]; do
  if curl -s -o /dev/null http://127.0.0.1:${PORT:-11434}/api/version; then break; fi
  i=$((i+1)); sleep 1
done

for m in $(echo "${OLLAMA_MODELS:-qwen2.5:0.5b}" | tr ',' ' '); do
  echo "[arc-ollama] pulling $m ..."
  ollama pull "$m" || echo "[arc-ollama] WARN: pull failed for $m"
done

wait $SERVER_PID
