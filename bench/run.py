"""Launches the packaged apps, times start-up and IPC, and reads every process's memory before quitting them.

python3 bench/run.py startup        -> runs/startup.jsonl        idle memory, with and without MCP
python3 bench/run.py startup-times  -> runs/startup-times.jsonl  time to script and to first frame
python3 bench/run.py ipc            -> runs/ipc.jsonl            every IPC method at 1, 10 and 50 MB
python3 bench/run.py no-isolation   -> runs/ipc-no-isolation.jsonl  Electron with context isolation off
python3 bench/run.py held           -> runs/ipc-held.jsonl         rows the backend already holds as objects
python3 bench/run.py channel-resolve -> runs/ipc-channel-resolve.jsonl  chunks received when invoke() resolves
python3 bench/run.py hidden         -> runs/startup-hidden.jsonl  first frame with the window hidden
python3 bench/run.py channel-raw    -> runs/ipc-channel-raw.jsonl  Channel of &[u8] against Channel of ipc::Response
python3 bench/run.py channel-chunks -> runs/ipc-channel-chunks.jsonl  Tauri Channel with 64 KiB, 1 MiB and 8 MiB chunks
"""
import json
import os
import queue
import signal
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import procmem  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / 'runs'
APPS = {
    'tauri': ROOT / 'tauri-app/target/release/bundle/macos/Tauri Bench.app/Contents/MacOS/tauri-bench',
    'electron': ROOT / 'electron-app/dist/Electron Bench-darwin-arm64/Electron Bench.app/Contents/MacOS/Electron Bench',
}
SERVER = ROOT / 'mcp-server/server.mjs'
METHODS = {
    'tauri': ['first-page', 'serde-struct', 'string', 'vec-u8', 'raw-response', 'channel', 'protocol', 'mcp-string', 'mcp-raw'],
    'electron': ['first-page', 'object', 'string', 'buffer', 'protocol', 'mcp-string', 'mcp-object'],
}


def role(args, app):
    """Names a process the way Activity Monitor would group it."""
    if str(SERVER) in args:
        return 'mcp-server'
    for name in ('WebContent', 'GPU', 'Networking'):
        if f'com.apple.WebKit.{name}' in args:
            return f'webkit-{name.lower()}'
    if '--type=renderer' in args:
        return 'renderer'
    if '--type=gpu-process' in args:
        return 'gpu'
    if '--type=utility' in args:
        return 'utility'
    if '--type=' in args:
        return 'helper'
    return 'app'


def owned(app_pid, before):
    """The app, its descendants, and the WebKit services started for it.

    launchd starts WebKit's processes, so they are not children. macOS charges them to the app's responsible
    process, which for an app started from a terminal is the terminal, not the app. So: WebKit processes that
    are new since launch and share the app's responsible process (Mail's or Safari's have their own)."""
    table = procmem.processes()
    pids = {app_pid}
    grown = True
    while grown:
        children = {pid for pid, (ppid, _) in table.items() if ppid in pids} - pids
        pids |= children
        grown = bool(children)
    owner = procmem.responsible(app_pid)
    pids |= {pid for pid, (_, args) in table.items()
             if pid not in before and 'com.apple.WebKit.' in args and procmem.responsible(pid) == owner}
    return {pid: table[pid][1] for pid in pids if pid in table}


def measure(app_pid, before, app):
    procs = []
    for pid, args in owned(app_pid, before).items():
        usage = procmem.usage(pid)
        if usage is not None:
            footprint, peak, resident = usage
            procs.append({'pid': pid, 'role': role(args, app), 'footprint': footprint, 'peak': peak, 'resident': resident})
    return procs


def launch(app, env_extra, wait_for, timeout=180, settle=0.0):
    before = set(procmem.processes())
    env = dict(os.environ, BENCH_PAYLOADS=str(ROOT / 'payloads'), MCP_SERVER=str(SERVER), **env_extra)
    out_file = RUNS / '.results.jsonl'
    out_file.unlink(missing_ok=True)
    env['BENCH_OUT'] = str(out_file)
    started = time.perf_counter()
    proc = subprocess.Popen([str(APPS[app])], env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                            start_new_session=True)
    lines = queue.Queue()
    threading.Thread(target=lambda: [lines.put((time.perf_counter(), l.strip())) for l in proc.stdout], daemon=True).start()
    marks = {}
    page = {}
    deadline = started + timeout
    while wait_for not in marks and time.perf_counter() < deadline:
        try:
            at, line = lines.get(timeout=0.5)
            if line.startswith('MARK '):
                name, *rest = line[5:].split(' ')
                marks.setdefault(name, at - started)
                page[name] = rest
            else:
                marks.setdefault(line, at - started)
        except queue.Empty:
            if proc.poll() is not None:
                break
    time.sleep(settle)
    procs = measure(proc.pid, before, app)
    os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
    # WebKit services outlive a killed Tauri app for a moment; wait so the next launch does not count them.
    for _ in range(50):
        if not any(p for p in procs if procmem.usage(p['pid']) is not None):
            break
        time.sleep(0.1)
    results = [json.loads(l) for l in out_file.read_text().splitlines()] if out_file.exists() else []
    return {'ready_s': marks.get('READY'), 'script_s': marks.get('script'), 'frame_s': marks.get('frame'),
            'page_marks': page, 'finished': wait_for in marks, 'procs': procs, 'results': results}


def startup_times(n):
    """Start-up time alone: launches alternate between the apps and quit right after the first frame."""
    with open(RUNS / 'startup-times.jsonl', 'a') as f:
        for i in range(n):
            for app in APPS:
                r = launch(app, {'BENCH_MODE': 'startup'}, 'READY', timeout=120, settle=0.5)
                row = {'app': app, 'launch': i + 1, 'ready_s': r['ready_s'], 'script_s': r['script_s'],
                       'frame_s': r['frame_s'], 'page_marks': r['page_marks']}
                f.write(json.dumps(row) + '\n')
                f.flush()
                print(row, flush=True)


def startup(n):
    """Idle memory: each app with and without an MCP client, measured 5 s after the first frame."""
    with open(RUNS / 'startup.jsonl', 'a') as f:
        for i in range(n):
            for mcp in ('0', '1'):
                for app in APPS:
                    r = launch(app, {'BENCH_MODE': 'startup', 'MCP': mcp}, 'READY', settle=5.0)
                    row = {'app': app, 'mcp': '1' == mcp, 'launch': i + 1, **r}
                    f.write(json.dumps(row) + '\n')
                    f.flush()
                    app_mib = sum(p['footprint'] for p in r['procs'] if 'mcp-server' != p['role']) / 2**20
                    print(f"{app:8} mcp={mcp} #{i + 1} script {r['script_s']:.3f} ready {r['ready_s']:.3f} s {r['page_marks']}, "
                          f"{app_mib:.1f} MiB", flush=True)


def ipc(sizes, reps, extra_env=None, out='ipc.jsonl'):
    with open(RUNS / out, 'a') as f:
        for mb in sizes:
            for app, methods in METHODS.items():
                for method in methods:
                    env = {'BENCH_MODE': 'ipc', 'BENCH_METHOD': method, 'BENCH_MB': str(mb), 'BENCH_REPS': str(reps),
                           **(extra_env or {})}
                    r = launch(app, env, 'DONE')
                    row = {'app': app, 'method': method, 'mb': mb, 'env': extra_env or {}, **r}
                    f.write(json.dumps(row) + '\n')
                    f.flush()
                    totals = [x['total_ms'] for x in r['results'] if 'total_ms' in x]
                    errors = [x['error'] for x in r['results'] if 'error' in x]
                    peak = sum(p['peak'] for p in r['procs'] if 'mcp-server' != p['role']) / 2**20
                    median = statistics.median(totals[1:]) if len(totals) > 1 else None
                    print(f"{app:8} {method:13} {mb:3} MB median {median} ms, peak sum {peak:.0f} MiB {errors[:1]}",
                          flush=True)


if __name__ == '__main__':
    RUNS.mkdir(exist_ok=True)
    if 'startup' == sys.argv[1]:
        startup(int(sys.argv[2]) if len(sys.argv) > 2 else 10)
    elif 'startup-times' == sys.argv[1]:
        startup_times(int(sys.argv[2]) if len(sys.argv) > 2 else 30)
    elif 'held' == sys.argv[1]:
        METHODS.clear()
        METHODS['tauri'] = ['held-struct', 'held-bytes']
        METHODS['electron'] = ['held-object', 'held-string']
        ipc([50], 6, None, 'ipc-held.jsonl')
    elif 'channel-resolve' == sys.argv[1]:
        METHODS.clear()
        METHODS['tauri'] = ['channel']
        ipc([1, 10, 50], 3, None, 'ipc-channel-resolve.jsonl')
    elif 'hidden' == sys.argv[1]:
        # Start-up with the window hidden: does each engine still draw a first frame?
        with open(RUNS / 'startup-hidden.jsonl', 'a') as f:
            for i in range(5):
                for app in APPS:
                    for hidden in ('0', '1'):
                        r = launch(app, {'BENCH_MODE': 'startup', 'BENCH_HIDDEN': hidden}, 'READY', timeout=20, settle=0.2)
                        row = {'app': app, 'hidden': '1' == hidden, 'launch': i + 1, 'script_s': r['script_s'],
                               'frame_s': r['frame_s'], 'page_marks': r['page_marks']}
                        f.write(json.dumps(row) + '\n')
                        f.flush()
                        print(row, flush=True)
    elif 'channel-raw' == sys.argv[1]:
        METHODS.clear()
        METHODS['tauri'] = ['channel', 'channel-raw']
        ipc([1, 10, 50], 6, None, 'ipc-channel-raw.jsonl')
    elif 'channel-chunks' == sys.argv[1]:
        METHODS.clear()
        METHODS['tauri'] = ['channel']
        for kib in (64, 1024, 8192):
            ipc([50], 6, {'BENCH_CHUNK_KIB': str(kib)}, 'ipc-channel-chunks.jsonl')
    elif 'no-isolation' == sys.argv[1]:
        METHODS.clear()
        METHODS['electron'] = ['object', 'string', 'buffer']
        ipc([50], 6, {'BENCH_NO_ISOLATION': '1'}, 'ipc-no-isolation.jsonl')
    else:
        ipc([int(s) for s in (sys.argv[2] if len(sys.argv) > 2 else '1,10,50').split(',')],
            int(sys.argv[3]) if len(sys.argv) > 3 else 6)
