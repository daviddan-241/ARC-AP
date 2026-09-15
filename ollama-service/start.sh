#!/bin/sh
# ARC model host — pulls models (comma list from OLLAMA_MODELS) then serves.
# NOTE: the ollama image has NO curl — use `ollama list` to wait for the socket.
set -e
export OLLAMA_HOST="0.0.0.0:${PORT:-11434}"

ollama serve &
SERVER_PID=$!

i=0
while [ $i -lt 120 ]; do
  if ollama list >/dev/null 2>&1; then break; fi
  i=$((i+1)); sleep 1
done

for m in $(echo "${OLLAMA_MODELS:-smollm2:135m}" | tr ',' ' '); do
  echo "[arc-ollama] pulling $m ..."
  ollama pull "$m" || echo "[arc-ollama] WARN: pull failed for $m"
done

echo "[arc-ollama] models ready: $(ollama list)"
wait $SERVER_PID
