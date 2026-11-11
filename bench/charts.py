"""The article's interactive charts, as the site's chart specs, from runs/summary.json.

python3 bench/report.py && python3 bench/charts.py ../../public/blog
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SLUG = 'tauri-vs-electron-ipc-memory'
TAURI, ELECTRON = 0, 1
LABELS = {
    'tauri/first-page': ('Tauri · first 100 rows', TAURI),
    'tauri/raw-response': ('Tauri · ipc::Response', TAURI),
    'tauri/protocol': ('Tauri · custom protocol', TAURI),
    'tauri/serde-struct': ('Tauri · parse, Vec<Row>', TAURI),
    'tauri/string': ('Tauri · String', TAURI),
    'tauri/channel': ('Tauri · Channel of &[u8]', TAURI),
    'tauri/vec-u8': ('Tauri · Vec<u8>', TAURI),
    'electron/first-page': ('Electron · first 100 rows', ELECTRON),
    'electron/string': ('Electron · string', ELECTRON),
    'electron/buffer': ('Electron · Buffer', ELECTRON),
    'electron/protocol': ('Electron · protocol.handle', ELECTRON),
    'electron/object': ('Electron · parse, object', ELECTRON),
}


def mib(v):
    return f'{v:,} MiB'


def ipc_chart(s):
    bars = []
    for key, (label, slot) in LABELS.items():
        d = s['ipc'][key]['50']
        bars.append({
            'label': label,
            'value': round(d['total_ms_median']),
            'slot': slot,
            'details': [
                ['Fastest / slowest', f"{d['total_ms_min']:g} / {d['total_ms_max']:g} ms"],
                ['JSON.parse in the page', f"{d['parse_ms_median']:g} ms"],
                ['Peak, all processes', mib(d['peak_mib_sum'])],
                ['Peak, page process', mib(d['peak_mib_page'])],
            ],
        })
    bars.sort(key=lambda b: b['value'])
    return {
        'kind': 'bar',
        'title': '50 MiB of rows from the backend to a parsed array in the page',
        'subtitle': 'The backend starts from JSON text. Median of 5 calls after a warm-up. Cyan: Tauri 2.12. Orange: Electron 45.',
        'source': 'Source: runs/summary.json in the companion repository',
        'format': 'number',
        'unit': 'ms',
        'valueLabel': 'Median time',
        'x': {'max': 1200, 'step': 300, 'unit': 'ms'},
        'bars': bars,
    }


def memory_chart(s):
    names = {
        'tauri': ('Tauri · empty window', TAURI),
        'tauri+mcp': ('Tauri · with an MCP client', TAURI),
        'electron': ('Electron · empty window', ELECTRON),
        'electron+mcp': ('Electron · with an MCP client', ELECTRON),
    }
    role_names = {
        'app': 'App process', 'webkit-webcontent': 'WebKit page', 'webkit-gpu': 'WebKit GPU',
        'webkit-networking': 'WebKit networking', 'renderer': 'Renderer (page)', 'gpu': 'GPU', 'utility': 'Network utility',
    }
    bars = []
    for key, (label, slot) in names.items():
        d = s['startup'][key]
        details = [[role_names[r], f'{v:g} MiB'] for r, v in d['roles_mib_median'].items()]
        if d['mcp_server_mib_median']:
            details.append(['MCP server (Node, not counted)', f"{d['mcp_server_mib_median']:g} MiB"])
        bars.append({'label': label, 'value': d['footprint_mib_median'], 'slot': slot, 'details': details})
    return {
        'kind': 'bar',
        'title': 'Memory of an idle window, all of the app\'s processes',
        'subtitle': 'Footprint as Activity Monitor shows it, median of 10 launches, 5 s after the first frame.',
        'source': 'Source: runs/summary.json in the companion repository',
        'format': 'number',
        'unit': 'MiB',
        'valueLabel': 'Footprint',
        'x': {'max': 120, 'step': 30, 'unit': 'MiB'},
        'bars': bars,
    }


if __name__ == '__main__':
    out = Path(sys.argv[1])
    summary = json.loads((ROOT / 'runs/summary.json').read_text())
    for n, spec in enumerate([memory_chart(summary), ipc_chart(summary)], 1):
        (out / f'{SLUG}-chart-{n}.json').write_text(json.dumps(spec, indent=1, ensure_ascii=False) + '\n')
        print(f'wrote {SLUG}-chart-{n}.json')
