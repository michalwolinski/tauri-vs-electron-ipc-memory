#!/usr/bin/env bash
# Sends one MCP tool call of the size you pick to both stdio clients, the TypeScript SDK and rmcp,
# and shows how long each took. Needs: node, cargo, and ./run.sh run once (or the steps it does).
#   ./play.sh 30         30 MiB (any whole number from 1 to 200)
set -euo pipefail
cd "$(dirname "$0")"
mb=${1:-30}
[ -f "payloads/rows-${mb}mb.json" ] || node bench/make-payloads.mjs "$mb" > /dev/null
[ -x tauri-app/target/release/examples/mcp_client ] || (cd tauri-app && cargo build --release --example mcp_client -q)

node --input-type=module -e "
import { spawnSync } from 'node:child_process';
const mb = ${mb};
const runs = [
  ['TypeScript SDK, default limit', 'node', ['bench/mcp-sdk-client.mjs', 'default', String(mb)]],
  ['TypeScript SDK, limit raised', 'node', ['bench/mcp-sdk-client.mjs', 'raised', String(mb)]],
  ['TypeScript SDK, linear buffer', 'node', ['bench/mcp-sdk-client.mjs', 'linear', String(mb)]],
  ['rmcp, default limit', 'tauri-app/target/release/examples/mcp_client', ['mcp-server/server.mjs', 'default', String(mb)]],
  ['rmcp, limit raised', 'tauri-app/target/release/examples/mcp_client', ['mcp-server/server.mjs', 'raised', String(mb)]],
];
console.log('One ' + mb + ' MiB tool result over stdio:\n');
const results = runs.map(([name, cmd, args]) => {
  const out = spawnSync(cmd, args, { encoding: 'utf8' }).stdout.trim().split('\n').map((l) => JSON.parse(l));
  return [name, out.find((r) => r.mb === mb)];
});
const longest = Math.max(...results.filter(([, r]) => !r.error).map(([, r]) => r.ms));
for (const [name, r] of results) {
  const label = name.padEnd(31);
  if (r.error) console.log(label + ' x ' + r.error);
  else console.log(label + ' ' + '#'.repeat(Math.max(1, Math.round((r.ms / longest) * 40))).padEnd(41) + Math.round(r.ms) + ' ms');
}
"
