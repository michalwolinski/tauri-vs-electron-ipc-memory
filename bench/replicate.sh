#!/usr/bin/env bash
# A second run of the headline measurements, on apps built from scratch the way README says.
# Run it in a clean copy of this repository (no node_modules, no target/, no dist/):
#   bench/replicate.sh        writes runs/replication/
set -euo pipefail
cd "$(dirname "$0")/.."
node bench/make-payloads.mjs 1,10,50
(cd mcp-server && npm ci --silent)
(cd electron-app && npm ci --silent && rm -rf ui && cp -R ../ui ui \
  && npx @electron/packager . "Electron Bench" --platform=darwin --arch=arm64 --out=dist --overwrite --ignore='^/dist' >/dev/null)
(cd tauri-app && npm ci --silent && npx tauri build --bundles app >/dev/null 2>&1 && cargo build --release --example mcp_client -q)
rm -rf runs/replication && mkdir -p runs/replication
python3 - <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, 'bench')
import run
run.RUNS = Path('runs/replication')
run.METHODS = {
    'tauri': ['raw-response', 'protocol', 'serde-struct', 'vec-u8', 'channel', 'first-page', 'mcp-raw'],
    'electron': ['string', 'buffer', 'object', 'first-page', 'mcp-string'],
}
run.ipc([50], 6)
run.startup(5)
PY
for mode in default raised linear; do node bench/mcp-sdk-client.mjs "$mode" >> runs/replication/mcp-sdk.jsonl; done
for mode in default raised; do tauri-app/target/release/examples/mcp_client mcp-server/server.mjs "$mode" >> runs/replication/mcp-rmcp.jsonl; done
