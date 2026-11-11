"""Turns runs/*.jsonl into runs/summary.json: every number the article quotes comes from here."""
import json
import statistics
import subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / 'runs'
MIB = 2 ** 20
PAGE = {'tauri': 'webkit-webcontent', 'electron': 'renderer'}


def rows(name):
    return [json.loads(line) for line in (RUNS / name).read_text().splitlines()]


def app_procs(procs):
    return [p for p in procs if 'mcp-server' != p['role']]


def by_role(procs, key):
    roles = defaultdict(float)
    for p in app_procs(procs):
        roles[p['role']] += p[key] / MIB
    return roles


def startup(name='startup.jsonl'):
    groups = defaultdict(list)
    for r in rows(name):
        groups[(r['app'], r['mcp'])].append(r)
    out = {}
    for (app, mcp), runs in sorted(groups.items()):
        ready = sorted(r['ready_s'] for r in runs)
        totals = [sum(by_role(r['procs'], 'footprint').values()) for r in runs]
        roles = defaultdict(list)
        for r in runs:
            for role, mib in by_role(r['procs'], 'footprint').items():
                roles[role].append(mib)
        server = [p['footprint'] / MIB for r in runs for p in r['procs'] if 'mcp-server' == p['role']]
        out[f"{app}{'+mcp' if mcp else ''}"] = {
            'launches': len(runs),
            'ready_ms_median': round(statistics.median(ready) * 1000),
            'ready_ms_min': round(ready[0] * 1000),
            'ready_ms_max': round(ready[-1] * 1000),
            'footprint_mib_median': round(statistics.median(totals), 1),
            'footprint_mib_min': round(min(totals), 1),
            'footprint_mib_max': round(max(totals), 1),
            'roles_mib_median': {k: round(statistics.median(v), 1) for k, v in sorted(roles.items())},
            'mcp_server_mib_median': round(statistics.median(server), 1) if server else None,
        }
    return out


def startup_times():
    out = {}
    all_rows = rows('startup-times.jsonl')
    for app in ('tauri', 'electron'):
        runs = [r for r in all_rows if app == r['app']]
        script = [r['script_s'] * 1000 for r in runs]
        frame = [r['frame_s'] * 1000 for r in runs]
        out[app] = {
            'launches': len(runs),
            'script_ms_median': round(statistics.median(script)),
            'frame_ms_median': round(statistics.median(frame)),
            'frame_after_script_ms_median': round(statistics.median(f - s for f, s in zip(frame, script))),
            'frames_over_1s': [round(f / 1000, 1) for f in frame if f > 1000],
        }
    return out


def ipc(name='ipc.jsonl'):
    out = defaultdict(dict)
    for r in rows(name):
        results = [x for x in r['results'] if 'total_ms' in x]
        errors = [x['error'] for x in r['results'] if 'error' in x]
        timed = results[1:]  # the first call warms up the page and the backend
        peaks = by_role(r['procs'], 'peak')
        out[f"{r['app']}/{r['method']}"][str(r['mb'])] = {
            'calls': len(results),
            'errors': errors,
            'total_ms_median': round(statistics.median(x['total_ms'] for x in timed), 1) if timed else None,
            'total_ms_min': round(min(x['total_ms'] for x in timed), 1) if timed else None,
            'total_ms_max': round(max(x['total_ms'] for x in timed), 1) if timed else None,
            'transfer_ms_median': round(statistics.median(x['transfer_ms'] for x in timed), 1) if timed else None,
            'parse_ms_median': round(statistics.median(x['parse_ms'] for x in timed), 1) if timed else None,
            'rows': sorted({x['rows'] for x in results}),
            'checksums': sorted({x['checksum'] for x in results}),
            'peak_mib_sum': round(sum(peaks.values())),
            'peak_mib_page': round(peaks.get(PAGE[r['app']], 0)),
            'peak_mib_backend': round(peaks.get('app', 0)),
        }
    return out


def bundles():
    """Measures the built app bundles into runs/bundle-sizes.json; without a build, reads that file."""
    saved = RUNS / 'bundle-sizes.json'
    paths = {
        'tauri': ROOT / 'tauri-app/target/release/bundle/macos/Tauri Bench.app',
        'electron': ROOT / 'electron-app/dist/Electron Bench-darwin-arm64/Electron Bench.app',
    }
    sizes = {}
    for app, path in paths.items():
        if path.exists():
            kib = int(subprocess.run(['du', '-sk', str(path)], capture_output=True, text=True).stdout.split()[0])
            sizes[app] = round(kib / 1024, 1)
    if len(paths) == len(sizes):
        saved.write_text(json.dumps(sizes) + '\n')
        return sizes
    return json.loads(saved.read_text())


def sdk():
    out = {}
    for name in ('mcp-sdk.jsonl', 'mcp-rmcp.jsonl'):
        path = RUNS / name
        if path.exists():
            out[name.removesuffix('.jsonl')] = rows(name)
    return out


if __name__ == '__main__':
    summary = {
        'startup': startup(),
        'startup_times': startup_times(),
        'ipc': ipc(),
        'ipc_no_isolation': ipc('ipc-no-isolation.jsonl'),
        'ipc_held': ipc('ipc-held.jsonl'),
        'channel_raw': [{'method': r['method'], 'mb': r['mb'], 'finished': r['finished'],
                         'script': r['page_marks'].get('script'), 'frame': r['page_marks'].get('frame'),
                         'chunk_types': sorted({t for x in r['results'] for t in x.get('chunk_types', [])}),
                         'total_ms_median': round(statistics.median(x['total_ms'] for x in r['results'][1:]), 1) if len(r['results']) > 1 else None,
                         'checksums': sorted({x['checksum'] for x in r['results']})}
                        for r in rows('ipc-channel-raw.jsonl')],
        'startup_hidden': rows('startup-hidden.jsonl'),
        'channel_chunks': {r['env']['BENCH_CHUNK_KIB']: round(statistics.median(x['total_ms'] for x in r['results'][1:]), 1)
                           for r in rows('ipc-channel-chunks.jsonl')},
        'channel_resolve': {str(r['mb']): [[x['chunks_when_invoke_resolved'], x['chunks']] for x in r['results']]
                            for r in rows('ipc-channel-resolve.jsonl')},
        'mcp_csv': {'calls': rows('mcp-csv.jsonl'), 'wire': rows('mcp-csv-wire.jsonl')},
        'mcp_limits': {'calls': rows('mcp-limits.jsonl'), 'wire': rows('mcp-limits-wire.jsonl')},
        'bundle_mib': bundles(),
        'mcp_clients': sdk(),
        'replication': {
            'ipc': ipc('replication/ipc.jsonl'),
            'startup': startup('replication/startup.jsonl'),
            'mcp_clients': {k: rows(f'replication/{k}.jsonl') for k in ('mcp-sdk', 'mcp-rmcp')},
        },
        'milo': json.loads((RUNS / 'milo-snapshot.json').read_text()),
    }
    (RUNS / 'summary.json').write_text(json.dumps(summary, indent=1) + '\n')
    print(json.dumps({k: summary[k] for k in ('startup', 'startup_times', 'bundle_mib')}, indent=1))
