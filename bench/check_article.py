"""Checks that the article quotes every measured number as runs/summary.json computes it.

python3 bench/report.py && python3 bench/check_article.py ../tauri-vs-electron-ipc-memory.html
Each claim is a fragment of the article's text with the numbers filled in from the runs. A fragment that is
missing means the article and the runs disagree.
"""
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
s = json.loads((ROOT / 'runs/summary.json').read_text())
st, times, ipc, iso, mcp = s['startup'], s['startup_times'], s['ipc'], s['ipc_no_isolation'], s['mcp_clients']


def ms(key, mb='50', field='total_ms_median', source=None):
    v = (source or ipc)[key][mb][field]
    return f'{v:,.0f}' if v >= 10 else f'{v:.1f}'.rstrip('0').rstrip('.')


def peak(key, mb='50', field='peak_mib_page'):
    return f"{ipc[key][mb][field]:,}"


def client(name, mode, mb, nth=0):
    hits = [r for r in mcp[name] if mode == r.get('mode') and mb == r.get('mb')]
    r = hits[nth]
    if 'error' in r:
        return r['error']
    return f"{r['ms']:,.0f}" if r['ms'] >= 100 else f"{r['ms']:.1f}".removesuffix('.0')


tauri, electron = st['tauri'], st['electron']
idle_gap = round(electron['footprint_mib_median'] - tauri['footprint_mib_median'], 1)
mcp_gap = round(st['electron+mcp']['footprint_mib_median'] - electron['footprint_mib_median'], 1)
main_gap = round(st['electron+mcp']['roles_mib_median']['app'] - electron['roles_mib_median']['app'], 1)
disk = s['bundle_mib']
# runs/mcp-wire-size.txt: payload MiB, text bytes, JSON-RPC line bytes, ratio
wire_rows = {int(r.split()[0]): r.split() for r in (ROOT / 'runs/mcp-wire-size.txt').read_text().splitlines()}
wire = int(wire_rows[50][2])
stall_row = next(json.loads(l) for l in (ROOT / 'runs/startup-times.jsonl').read_text().splitlines()
                 if json.loads(l)['frame_s'] > 1)
stalls_memory = [r for r in (json.loads(l) for l in (ROOT / 'runs/startup.jsonl').read_text().splitlines())
                 if 'tauri' == r['app'] and r['ready_s'] > 1]
stalls = sorted([f"{r['ready_s']:.1f}" for r in stalls_memory] + [f'{x:.1f}' for x in times['tauri']['frames_over_1s']],
                key=float)
electron_stalls = [r for r in (json.loads(l) for l in (ROOT / 'runs/startup.jsonl').read_text().splitlines())
                   if 'electron' == r['app'] and r['ready_s'] > 1]
milo = s['milo']
milo_page = next(p for p in milo['processes'] if 'WebContent' in p['process'])

claims = [
    f"Tauri used {idle_gap} MiB less at idle",
    f"took {tauri['footprint_mib_median']} MiB on Tauri and {electron['footprint_mib_median']} MiB on Electron",
    f"added {mcp_gap} MiB to Electron",
    f"took about {round(min(st['tauri+mcp']['mcp_server_mib_median'], st['electron+mcp']['mcp_server_mib_median']))} MiB: more than Tauri",
    f"ran after {times['tauri']['script_ms_median']} ms on Tauri and {times['electron']['script_ms_median']} ms on Electron (median of {times['tauri']['launches']} launches)",
    f"came at {times['tauri']['frame_ms_median']} and {times['electron']['frame_ms_median']} ms",
    f"In {len(stalls)} of {times['tauri']['launches'] + tauri['launches'] + st['tauri+mcp']['launches']} Tauri launches WebKit held the first frame back for {round(float(stalls[0]))} to {round(float(stalls[-1]))} seconds",
    f"in {ms('tauri/raw-response')} ms through Tauri",
    f"in {ms('electron/string')} ms as an Electron string",
    f"Parsing it in the backend and returning objects took {ms('tauri/serde-struct')} ms on Tauri and {ms('electron/object')} ms on Electron",
    f"{ms('tauri/vec-u8')} ms and a {ipc['tauri/vec-u8']['50']['peak_mib_page'] / 1024:.1f} GiB page process for 50 MiB",
    f"took {ipc['electron/mcp-string']['50']['total_ms_median'] / 1000:.1f} s to reach the Electron page",
    f"read the same result in {float(client('mcp-rmcp', 'raised', 50)) / 1000:.2f} s",
    f"<td>Tauri 2.12.5, <code>@tauri-apps/cli</code> 2.12.4</td>",
    f"<td>{disk['tauri']} MiB</td><td>{disk['electron']} MiB</td>",
    f"1 MiB ({ipc['tauri/raw-response']['1']['rows'][0]:,} rows), 10 MiB ({ipc['tauri/raw-response']['10']['rows'][0]:,} rows) and 50 MiB ({ipc['tauri/raw-response']['50']['rows'][0]:,} rows)",
    f"<td>App / main process</td><td>{tauri['roles_mib_median']['app']} MiB</td><td>{electron['roles_mib_median']['app']} MiB</td>",
    f"<td>App / main process with the MCP client</td><td>{st['tauri+mcp']['roles_mib_median']['app']} MiB</td><td>{st['electron+mcp']['roles_mib_median']['app']} MiB</td>",
    f"<td>{tauri['roles_mib_median']['webkit-webcontent']} MiB</td><td>{electron['roles_mib_median']['renderer']} MiB</td>",
    f"<td>GPU</td><td>{tauri['roles_mib_median']['webkit-gpu']} MiB</td><td>{electron['roles_mib_median']['gpu']} MiB</td>",
    f"<td>Network</td><td>{tauri['roles_mib_median']['webkit-networking']} MiB</td><td>{electron['roles_mib_median']['utility']} MiB</td>",
    f"<td><strong>{tauri['footprint_mib_median']} MiB</strong></td><td><strong>{electron['footprint_mib_median']} MiB</strong>",
    f"<td><strong>{st['tauri+mcp']['footprint_mib_median']} MiB</strong></td><td><strong>{st['electron+mcp']['footprint_mib_median']} MiB</strong>",
    f"ranged from {electron['footprint_mib_min']} to {electron['footprint_mib_max']} MiB, Tauri's from {tauri['footprint_mib_min']} to {tauri['footprint_mib_max']} MiB",
    f"the {disk['electron'] - disk['tauri']:.0f} MiB of disk",
    f"stayed at {round(st['tauri+mcp']['roles_mib_median']['app'])} MiB with it connected",
    f"{main_gap} MiB more there",
    f"<td>{times['tauri']['script_ms_median']} ms</td><td>{times['electron']['script_ms_median']} ms</td>",
    f"<td>{times['tauri']['frame_ms_median']} ms</td><td>{times['electron']['frame_ms_median']} ms</td>",
    f"<td>{times['tauri']['frame_after_script_ms_median']} ms</td><td>{times['electron']['frame_after_script_ms_median']} ms</td>",
    f"{len(stalls)} of 50 launches: " + ', '.join(f'{x} s' for x in stalls),
    f"<td>0 of 50</td>" if 0 == len(electron_stalls) else 'MISMATCH electron stalls',
    f"was {st['tauri+mcp']['ready_ms_median']} ms on Tauri and {st['electron+mcp']['ready_ms_median']} ms on Electron, against {tauri['ready_ms_median']} and {electron['ready_ms_median']} ms without it",
    f"WebKit's comes {times['tauri']['frame_after_script_ms_median']} ms after the script",
    f"the script ran at {stall_row['page_marks']['script'][0]} ms and the frame came at {int(stall_row['page_marks']['frame'][0]):,} ms, with <code>document.visibilityState</code> reporting <code>{stall_row['page_marks']['frame'][1]}</code>",
    f"In the {stall_row['frame_s']:.1f} s launch",
    f"ranged from {ms('electron/protocol', '10', 'total_ms_min')} to {ms('electron/protocol', '10', 'total_ms_max')} ms",
    f"took {ms('tauri/raw-response', field='transfer_ms_median')} ms to deliver 50 MiB to the page, and Electron's string {ms('electron/string', field='transfer_ms_median')} ms",
    f"took {ms('tauri/raw-response', field='parse_ms_median')} ms in WebKit and {ms('electron/string', field='parse_ms_median')} ms in V8",
    f"parsed again by the webview: {ms('tauri/serde-struct')} ms",
    f"was no better, {ms('tauri/string')} ms",
    f"peak of {peak('tauri/serde-struct')} to {peak('tauri/raw-response')} MiB, and to {peak('tauri/vec-u8')} MiB",
    f"The lowest of those, {peak('tauri/serde-struct')} MiB",
    f"kept the page at {peak('electron/first-page')} and {peak('tauri/first-page')} MiB and took {ms('electron/first-page')} and {ms('tauri/first-page')} ms",
    f"At 50 MiB that took {ms('tauri/vec-u8')} ms, the page process peaked at {peak('tauri/vec-u8')} MiB, and all of the app's processes together at {peak('tauri/vec-u8', field='peak_mib_sum')} MiB",
    f"route: {ms('tauri/channel')} ms for 50 MiB, against {ms('tauri/raw-response')} ms for one",
    f"Waiting for them takes {ms('tauri/channel')} ms",
    f"the slowest Electron route: {ms('electron/object')} ms for 50 MiB",
    f"<td>{ms('electron/object')} ms</td><td>{ms('electron/object', source=iso)} ms</td>",
    f"<td>{ms('electron/string')} ms</td><td>{ms('electron/string', source=iso)} ms</td>",
    f"<td>{ms('electron/buffer')} ms</td><td>{ms('electron/buffer', source=iso)} ms</td>",
    f"rebuilding {ipc['electron/object']['50']['rows'][0]:,} objects",
    f"<th>Backend holds {ipc['electron/object']['50']['rows'][0]:,} rows, 50 MiB as JSON</th>",
    f"took {ms('tauri/raw-response', field='transfer_ms_median')} to {ms('electron/buffer', field='transfer_ms_median')} ms of the {ms('electron/string')} to {ms('electron/buffer')}",
    f"was a {wire / 2**20:.1f} MiB line",
    f"in {ms('tauri/mcp-raw')} ms on Tauri (rmcp, then <code>ipc::Response</code>) and in {ms('electron/mcp-string')} ms on Electron",
    f"<td>TypeScript SDK, default limit</td><td>{client('mcp-sdk', 'default', 1)} ms</td><td>\"Connection closed\"</td>"
    if 'Connection closed' in client('mcp-sdk', 'default', 10) and 'Not connected' == client('mcp-sdk', 'default', 50) else 'MISMATCH sdk default',
    f"<td>TypeScript SDK, limit raised to 256 MiB</td><td>{client('mcp-sdk', 'raised', 1)} ms</td><td>{client('mcp-sdk', 'raised', 10)} ms</td><td>{client('mcp-sdk', 'raised', 50)} ms</td><td>{client('mcp-sdk', 'raised', 1, 1)} ms</td>",
    f"<td>TypeScript SDK, linear read buffer</td><td>{client('mcp-sdk', 'linear', 1)} ms</td><td>{client('mcp-sdk', 'linear', 10)} ms</td><td>{client('mcp-sdk', 'linear', 50)} ms</td><td>{client('mcp-sdk', 'linear', 1, 1)} ms</td>",
    f"<td>rmcp, default limit</td><td>{client('mcp-rmcp', 'default', 1)} ms</td><td>{client('mcp-rmcp', 'default', 10)} ms</td><td>{client('mcp-rmcp', 'default', 50)}</td><td>{client('mcp-rmcp', 'default', 1, 1)} ms</td>",
    f"<td>rmcp, limit raised to 256 MiB</td><td>{client('mcp-rmcp', 'raised', 1)} ms</td><td>{client('mcp-rmcp', 'raised', 10)} ms</td><td>{client('mcp-rmcp', 'raised', 50)} ms</td><td>{client('mcp-rmcp', 'raised', 1, 1)} ms</td>",
    f"5 times the data took {float(client('mcp-sdk', 'raised', 50).replace(',', '')) / float(client('mcp-sdk', 'raised', 10)):.0f} times as long",
    f"{client('mcp-sdk', 'linear', 50)} ms instead of {client('mcp-sdk', 'raised', 50)}",
    f"rmcp read 50 MiB in {client('mcp-rmcp', 'raised', 50)} ms",
    f"took {ms('tauri/mcp-string')} ms, with calls between {ms('tauri/mcp-string', field='total_ms_min')} and {ms('tauri/mcp-string', field='total_ms_max')} ms, while the same <code>String</code> route without MCP took {ms('tauri/string')} ms",
    f"The Rust process peaked at {peak('tauri/mcp-string', field='peak_mib_backend')} MiB on that route and at {peak('tauri/mcp-raw', field='peak_mib_backend')} MiB when it returned bytes, which took {ms('tauri/mcp-raw')} ms",
    f"running for {int(milo['uptime'].split('-')[0])} days and {int(milo['uptime'].split('-')[1].split(':')[0])} hours and took {milo['total_mib']} MiB, of which {milo_page['footprint_mib']} MiB was the WebKit page, whose lifetime peak was {milo_page['peak_mib']} MiB",
    f"{disk['tauri']} MiB against {disk['electron']} MiB on disk, and {idle_gap} MiB less at idle",
    f"kept the page process at {peak('electron/first-page')} to {peak('tauri/first-page')} MiB",
    f"an array of {int(wire_rows[50][1]) // 10**6} million numbers",
]

claims += [
    f"a page process at {peak('electron/first-page')} or {peak('tauri/first-page')} MiB instead of {peak('tauri/serde-struct')} to {peak('tauri/raw-response')}",
]

# The charts' alt texts name every bar with its value, as the chart specs in public/blog/ draw them.
sys.path.insert(0, str(Path(__file__).parent))
import charts  # noqa: E402

for bar in charts.ipc_chart(s)['bars']:
    claims.append(f"{bar['label'].replace(' · ', ' ')} {bar['value']:,} ms")
for bar in charts.memory_chart(s)['bars']:
    claims.append(f"{bar['label'].replace(' · ', ' ')} {bar['value']:g} MiB")

held = s['ipc_held']
claims += [
    f"<td>{ms('tauri/held-struct', source=held)} ms</td><td>{ms('tauri/held-struct', field='total_ms_min', source=held)} to {ms('tauri/held-struct', field='total_ms_max', source=held)} ms</td><td>{held['tauri/held-struct']['50']['peak_mib_page']} MiB</td>",
    f"<td>{ms('tauri/held-bytes', source=held)} ms</td><td>{ms('tauri/held-bytes', field='total_ms_min', source=held)} to {ms('tauri/held-bytes', field='total_ms_max', source=held)} ms</td><td>{held['tauri/held-bytes']['50']['peak_mib_page']} MiB</td>",
    f"<td>{ms('electron/held-object', source=held)} ms</td><td>{ms('electron/held-object', field='total_ms_min', source=held)} to {ms('electron/held-object', field='total_ms_max', source=held)} ms</td><td>{held['electron/held-object']['50']['peak_mib_page']} MiB</td>",
    f"<td>{ms('electron/held-string', source=held)} ms</td><td>{ms('electron/held-string', field='total_ms_min', source=held)} to {ms('electron/held-string', field='total_ms_max', source=held)} ms</td><td>{held['electron/held-string']['50']['peak_mib_page']} MiB</td>",
    f"Electron's object route stayed {['', 'one', 'two', 'three', 'four', 'five'][round(held['electron/held-object']['50']['total_ms_median'] / held['electron/held-string']['50']['total_ms_median'])]} times slower than a string",
]
assert held['tauri/held-struct']['50']['total_ms_median'] < held['tauri/held-bytes']['50']['total_ms_median']
assert 2 * held['tauri/held-struct']['50']['peak_mib_page'] < held['tauri/held-bytes']['50']['peak_mib_page']
for d in held.values():
    assert not d['50']['errors'] and 1 == len(d['50']['checksums']) and 6 == d['50']['calls']
resolve = s['channel_resolve']
assert all(0 == at for calls in resolve.values() for at, _ in calls)
csv_calls = {r['format']: r for r in s['mcp_csv']['calls']}
csv_wire = {r['format']: r for r in s['mcp_csv']['wire']}
assert 'Connection closed' in csv_calls['json']['error'] and 'error' not in csv_calls['csv']
claims += [
    f"0 in each of the {sum(len(c) for c in resolve.values())} calls at 1, 10 and 50 MiB, out of {resolve['1'][0][1]}, {resolve['10'][0][1]} and {resolve['50'][0][1]}",
    f"{csv_wire['json']['text_bytes']:,} bytes of JSON and {csv_wire['csv']['text_bytes']:,} bytes of CSV, both well under 10 MiB ({10 * 2**20:,} bytes)",
    f"which made the line {csv_wire['json']['line_bytes']:,} bytes: over the limit",
    f"so its line was {csv_wire['csv']['line_bytes']:,} bytes and the call returned normally",
]
raw = [r for r in s['channel_raw'] if r['finished'] and 50 == r['mb']]
by = {r['method']: r for r in raw if r['total_ms_median']}
assert ['Array'] == by['channel']['chunk_types'] and ['ArrayBuffer'] == by['channel-raw']['chunk_types']
assert by['channel']['checksums'] == by['channel-raw']['checksums'] == ipc['tauri/channel']['50']['checksums']
stalled_evening = [r for r in s['channel_raw'] if r['script'] and 2 == len(r['script'])]
hidden = s['startup_hidden']
def count(app, hid, cond):
    return sum(1 for r in hidden if app == r['app'] and hid == r['hidden'] and cond(r))
claims += [
    f"made the chunks arrive as <code>ArrayBuffer</code>s, and 50 MiB took {by['channel-raw']['total_ms_median']:,.0f} ms instead of {by['channel']['total_ms_median']:,.0f} in the same run",
    f"With the window hidden, WebKit drew no frame within 20 seconds in {count('tauri', True, lambda r: r['frame_s'] is None)} of {count('tauri', True, lambda r: True)} launches",
    f"Electron drew its first frame in {count('electron', True, lambda r: r['frame_s'] is not None and 'visible' == r['page_marks']['script'][1])} of {count('electron', True, lambda r: True)} hidden launches",
    f"And {['no', 'one', 'two', 'three'][count('tauri', False, lambda r: r['frame_s'] is None and 'hidden' == r['page_marks']['script'][1])]} of the five \"shown\" Tauri launches started <code>hidden</code>",
    f"{sum(1 for r in stalled_evening if 'hidden' == r['script'][1] and not r['frame'])} of {len(stalled_evening)} Tauri launches in a run started <code>hidden</code> and drew nothing",
]
assert all('hidden' == r['page_marks']['script'][1] for r in hidden if 'tauri' == r['app'] and r['hidden'])
chunks = s['channel_chunks']
limits = {(r['client'], r['mb']): r for r in s['mcp_limits']['calls']}
lines = {r['mb']: r['line_bytes'] / 2**20 for r in s['mcp_limits']['wire']}
assert 'error' not in limits[('typescript-sdk', 8)] and 'Connection closed' in limits[('typescript-sdk', 9)]['error']
assert 'error' not in limits[('rmcp', 14)] and 'no answer' in limits[('rmcp', 15)]['error']
assert lines[9] > 10 > lines[8] and lines[15] > 16 > lines[14]
claims += [
    f"with 64 KiB, 1 MiB and 8 MiB chunks the same transfer took {chunks['64']:,.0f}, {chunks['1024']:,.0f} and {chunks['8192']:,.0f} ms",
    f"8 MiB of text (a {lines[8]:.1f} MiB line) went through and 9 MiB of text (a {lines[9]:.1f} MiB line) closed the session",
    f"14 MiB of text (a {lines[14]:.1f} MiB line) went through and 15 MiB (a {lines[15]:.1f} MiB line) did not",
    f"about {round((wire / int(wire_rows[50][1]) - 1) * 100)}% more than the text here",
    f"The remaining {ms('electron/object', source=iso)} ms are the main process",
    f"sends almost nothing, took {ms('electron/first-page')} ms in total",
]

rep = s['replication']
s_rep = rep['ipc']
claims += [
    f"sent 100 of them in {ms('tauri/first-page')} ms, and in {ms('tauri/first-page', source=s_rep)} ms in the second run; V8 in Electron's main process did the same in {ms('electron/first-page')} and {ms('electron/first-page', source=s_rep)} ms",
    f"in a second run on fresh builds, {ms('tauri/raw-response', source=s_rep)} and {ms('electron/string', source=s_rep)} ms",
    f"Electron's string took {ms('electron/string', source=s_rep)} ms against Tauri's {ms('tauri/raw-response', source=s_rep)}",
    f"the string route took {ms('electron/string')} ms in one run and {ms('electron/string', source=s_rep)} ms in the other, the <code>Buffer</code> route {ms('electron/buffer')} and {ms('electron/buffer', source=s_rep)} ms",
]
rep_launches = [json.loads(l) for l in (ROOT / 'runs/replication/startup.jsonl').read_text().splitlines()]
assert 10 == len([r for r in rep_launches if 'tauri' == r['app']]) and all(r['ready_s'] < 1 for r in rep_launches)
for d in s_rep.values():
    assert not d['50']['errors'] and 1 == len(d['50']['checksums']) and 6 == d['50']['calls']
import subprocess
table = subprocess.run([sys.executable, str(Path(__file__).parent / 'replication_table.py')], capture_output=True, text=True, check=True).stdout
claims += [line.strip() for line in table.splitlines() if line.strip().startswith('<tr><td>')]
claims.append(f"None of the {len(rep_launches)} start-ups in the second run, {len(rep_launches) // 2} per app, stalled.")

# The IPC table, cell by cell.
for key, mbs in ipc.items():
    if key.split('/')[1] in ('mcp-raw', 'mcp-string', 'mcp-object'):
        continue
    cells = ''.join(f"<td>{ms(key, mb)} ms</td>" for mb in ('1', '10', '50'))
    claims.append(cells + f"<td>{peak(key)} MiB</td></tr>")

# Every run delivered every row, with the same checksum per size.
for key, mbs in {**ipc, **{f'no-isolation/{k}': v for k, v in iso.items()}}.items():
    for mb, d in mbs.items():
        assert not d['errors'], (key, mb, d['errors'])
        assert 1 == len(d['checksums']), (key, mb)
        assert 6 == d['calls'], (key, mb, d['calls'])

text = Path(sys.argv[1]).read_text()
flat = html.unescape(re.sub(r'\s+', ' ', text))

# Every code block is a verbatim excerpt of a file in this repository.
sources = [p.read_text() for p in ROOT.rglob('*') if p.is_file() and p.suffix in ('.rs', '.js', '.mjs')
           and 'node_modules' not in p.parts and 'target' not in p.parts and 'dist' not in p.parts]
blocks = [html.unescape(b) for b in re.findall(r'<pre><code[^>]*>(.*?)</code></pre>', text, re.S)]
for block in blocks:
    claims.append('code block found in the repository' if any(block in src for src in sources)
                  else 'CODE BLOCK NOT IN REPOSITORY: ' + block.splitlines()[0])
flat += ' code block found in the repository'
missing = [c for c in claims if html.unescape(c) not in flat]
for c in missing:
    print('MISSING:', c)
print(f'{len(claims) - len(missing)}/{len(claims)} claims found')
sys.exit(1 if missing else 0)
