#!/usr/bin/env bash
# Rebuilds both apps and reruns every measurement the article quotes, then checks the article against them.
# macOS only (the harness reads memory with proc_pid_rusage). Takes about an hour; keep the machine otherwise idle.
#   ./run.sh            everything
#   ./run.sh report     only recompute runs/summary.json and check the article
set -euo pipefail
cd "$(dirname "$0")"

article=../tauri-vs-electron-ipc-memory.html

if [ "${1:-}" != report ]; then
  node bench/make-payloads.mjs 1,10,50
  (cd mcp-server && npm ci)
  (cd electron-app && npm ci && rm -rf ui && cp -R ../ui ui \
    && npx @electron/packager . "Electron Bench" --platform=darwin --arch=arm64 --out=dist --overwrite --ignore='^/dist')
  (cd tauri-app && npm ci && npx tauri build --bundles app && cargo build --release --example mcp_client)

  rm -f runs/startup.jsonl runs/startup-times.jsonl runs/ipc.jsonl runs/ipc-no-isolation.jsonl \
    runs/mcp-sdk.jsonl runs/mcp-rmcp.jsonl
  python3 bench/run.py startup 10 | tee runs/startup.log
  python3 bench/run.py startup-times 30 | tee runs/startup-times.log
  python3 bench/run.py ipc 1,10,50 6 | tee runs/ipc.log
  python3 bench/run.py no-isolation | tee runs/ipc-no-isolation.log
  rm -f runs/ipc-held.jsonl runs/ipc-channel-chunks.jsonl runs/mcp-limits.jsonl
  python3 bench/run.py held | tee runs/ipc-held.log
  python3 bench/run.py channel-chunks | tee runs/ipc-channel-chunks.log
  rm -f runs/ipc-channel-resolve.jsonl runs/mcp-csv.jsonl runs/ipc-channel-raw.jsonl runs/startup-hidden.jsonl
  python3 bench/run.py channel-raw | tee runs/ipc-channel-raw.log
  python3 bench/run.py hidden | tee runs/startup-hidden.log
  python3 bench/run.py channel-resolve | tee runs/ipc-channel-resolve.log
  # The puzzle: 9 MiB of JSON and 9 MiB of CSV through the SDK's default limit.
  node bench/make-csv.mjs 9
  for format in json csv; do node bench/mcp-sdk-client.mjs default 9 "$format" | head -1 >> runs/mcp-csv.jsonl; done
  node -e "
    const fs = require('fs');
    for (const format of ['json', 'csv']) {
      const text = fs.readFileSync('payloads/rows-9mb.' + format, 'utf8');
      const line = JSON.stringify({ result: { content: [{ type: 'text', text }] }, jsonrpc: '2.0', id: 2 }) + '\\n';
      console.log(JSON.stringify({ format, text_bytes: text.length, line_bytes: Buffer.byteLength(line) }));
    }" > runs/mcp-csv-wire.jsonl
  # Just under and just over each client's default limit, with these rows.
  node bench/make-payloads.mjs 8,9,14,15
  for mb in 8 9; do
    node bench/mcp-sdk-client.mjs default "$mb" | head -1 | sed 's/^{/{"client":"typescript-sdk",/' >> runs/mcp-limits.jsonl
  done
  for mb in 14 15; do
    tauri-app/target/release/examples/mcp_client mcp-server/server.mjs default "$mb" | head -1 | sed 's/^{/{"client":"rmcp",/' >> runs/mcp-limits.jsonl
  done
  node -e "
    const fs = require('fs');
    for (const mb of [8, 9, 14, 15]) {
      const text = fs.readFileSync('payloads/rows-' + mb + 'mb.json', 'utf8');
      const line = JSON.stringify({ result: { content: [{ type: 'text', text }] }, jsonrpc: '2.0', id: 2 }) + '\\n';
      console.log(JSON.stringify({ mb, text_bytes: text.length, line_bytes: Buffer.byteLength(line) }));
    }" > runs/mcp-limits-wire.jsonl
  for mode in default raised linear; do node bench/mcp-sdk-client.mjs "$mode" >> runs/mcp-sdk.jsonl; done
  for mode in default raised; do tauri-app/target/release/examples/mcp_client mcp-server/server.mjs "$mode" >> runs/mcp-rmcp.jsonl; done
  node -e "
    const fs = require('fs');
    for (const mb of [1, 10, 50]) {
      const text = fs.readFileSync('payloads/rows-' + mb + 'mb.json', 'utf8');
      const line = JSON.stringify({ result: { content: [{ type: 'text', text }] }, jsonrpc: '2.0', id: 2 }) + '\n';
      console.log(mb, text.length, Buffer.byteLength(line), (Buffer.byteLength(line) / text.length).toFixed(3));
    }" > runs/mcp-wire-size.txt
fi

python3 bench/report.py > /dev/null
if [ -f "$article" ]; then
  python3 bench/check_article.py "$article"
fi
