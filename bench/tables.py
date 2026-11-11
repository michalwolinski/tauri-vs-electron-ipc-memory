"""Prints the article's IPC table as HTML, from runs/summary.json."""
import json
from pathlib import Path

s = json.loads((Path(__file__).resolve().parent.parent / 'runs/summary.json').read_text())
ROWS = [
    ('tauri/serde-struct', 'Tauri', 'parse in Rust, return <code>Vec&lt;Row&gt;</code> through serde'),
    ('tauri/string', 'Tauri', '<code>String</code>, parsed in the page'),
    ('tauri/vec-u8', 'Tauri', '<code>Vec&lt;u8&gt;</code> without <code>Response</code>'),
    ('tauri/raw-response', 'Tauri', '<code>ipc::Response</code> (an <code>ArrayBuffer</code>)'),
    ('tauri/channel', 'Tauri', '<code>Channel</code>, 1 MiB chunks'),
    ('tauri/protocol', 'Tauri', 'custom protocol, read with <code>fetch</code>'),
    ('tauri/first-page', 'Tauri', 'parse in Rust, send the first 100 rows'),
    ('electron/object', 'Electron', 'parse in main, return the object through <code>invoke</code>'),
    ('electron/string', 'Electron', 'string, parsed in the page'),
    ('electron/buffer', 'Electron', '<code>Buffer</code> (a <code>Uint8Array</code>)'),
    ('electron/protocol', 'Electron', '<code>protocol.handle</code>, read with <code>fetch</code>'),
    ('electron/first-page', 'Electron', 'parse in main, send the first 100 rows'),
]


def ms(v):
    return f'{v:,.0f}' if v >= 10 else f'{v:.1f}'.rstrip('0').rstrip('.')


print('<table>\n  <thead><tr><th>App</th><th>How the rows travel</th><th>1 MiB</th><th>10 MiB</th><th>50 MiB</th>'
      '<th>Page peak at 50 MiB</th></tr></thead>\n  <tbody>')
for key, app, how in ROWS:
    d = s['ipc'][key]
    cells = ''.join(f"<td>{ms(d[mb]['total_ms_median'])} ms</td>" for mb in ('1', '10', '50'))
    print(f"    <tr><td>{app}</td><td>{how}</td>{cells}<td>{d['50']['peak_mib_page']:,} MiB</td></tr>")
print('  </tbody>\n</table>')
