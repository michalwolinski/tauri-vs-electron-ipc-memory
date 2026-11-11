"""Prints the article's repeatability table (first run against the replication) from runs/summary.json."""
import json
from pathlib import Path

s = json.loads((Path(__file__).resolve().parent.parent / 'runs/summary.json').read_text())
rep = s['replication']


def ms(v):
    return f'{v:,.0f} ms'


def client(rows, mode, mb=50):
    return next(r for r in rows if mode == r['mode'] and mb == r['mb'])['ms']


ROWS = [
    ('Idle, Tauri', f"{s['startup']['tauri']['footprint_mib_median']} MiB", f"{rep['startup']['tauri']['footprint_mib_median']} MiB"),
    ('Idle, Electron', f"{s['startup']['electron']['footprint_mib_median']} MiB", f"{rep['startup']['electron']['footprint_mib_median']} MiB"),
    ('Idle with an MCP client, Tauri', f"{s['startup']['tauri+mcp']['footprint_mib_median']} MiB", f"{rep['startup']['tauri+mcp']['footprint_mib_median']} MiB"),
    ('Idle with an MCP client, Electron', f"{s['startup']['electron+mcp']['footprint_mib_median']} MiB", f"{rep['startup']['electron+mcp']['footprint_mib_median']} MiB"),
]
for key, label in [
    ('tauri/raw-response', 'Tauri, <code>ipc::Response</code>'), ('tauri/protocol', 'Tauri, custom protocol'),
    ('tauri/serde-struct', 'Tauri, parse and return <code>Vec&lt;Row&gt;</code>'), ('tauri/vec-u8', 'Tauri, <code>Vec&lt;u8&gt;</code>'),
    ('tauri/channel', 'Tauri, <code>Channel</code>'), ('tauri/first-page', 'Tauri, first 100 rows'),
    ('tauri/mcp-raw', 'Tauri, MCP result as <code>ipc::Response</code>'),
    ('electron/string', 'Electron, string'), ('electron/buffer', 'Electron, <code>Buffer</code>'),
    ('electron/object', 'Electron, parse and return the object'), ('electron/first-page', 'Electron, first 100 rows'),
    ('electron/mcp-string', 'Electron, MCP result as a string'),
]:
    ROWS.append((f'50 MiB: {label}', ms(s['ipc'][key]['50']['total_ms_median']), ms(rep['ipc'][key]['50']['total_ms_median'])))
mc, rc = s['mcp_clients'], rep['mcp_clients']
ROWS += [
    ('TypeScript SDK alone, 50 MiB, limit raised', ms(client(mc['mcp-sdk'], 'raised')), ms(client(rc['mcp-sdk'], 'raised'))),
    ('TypeScript SDK alone, 50 MiB, linear buffer', ms(client(mc['mcp-sdk'], 'linear')), ms(client(rc['mcp-sdk'], 'linear'))),
    ('rmcp alone, 50 MiB, limit raised', ms(client(mc['mcp-rmcp'], 'raised')), ms(client(rc['mcp-rmcp'], 'raised'))),
]
print('<table>\n  <thead><tr><th>Measurement</th><th>First run</th><th>Second run, fresh builds</th></tr></thead>\n  <tbody>')
for label, a, b in ROWS:
    print(f'    <tr><td>{label}</td><td>{a}</td><td>{b}</td></tr>')
print('  </tbody>\n</table>')
