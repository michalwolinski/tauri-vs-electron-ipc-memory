# Tauri vs Electron: memory, start-up and IPC, measured

By [Michał Woliński](https://wolinski.com). Companion repository for the article
[Tauri vs Electron for an MCP Client: Memory, Start-up and Where IPC Lies, Measured](https://wolinski.com/blog/tauri-vs-electron-ipc-memory.html).

The same small desktop app, built twice: once on Tauri 2.12 and once on Electron 45. Both load the same page
(`ui/`), connect to the same stdio MCP server (`mcp-server/`) and move the same JSON payloads of 1, 10 and 50 MiB
from the backend to the page by every route each framework offers. A harness launches the packaged apps, times
them and reads the memory of every process each app owns. Every number in the article comes from the run files in
`runs/`, and `bench/check_article.py` checks the article against them.

## Layout

| Path | What it is |
| --- | --- |
| `ui/` | The page both apps load, its benchmark script and the Tauri bridge (`bridge-tauri.js`) and Electron bridge (`bridge-electron.js`) |
| `tauri-app/` | Tauri 2.12.5 app: IPC commands, a custom `bench://` protocol and an rmcp 3.9.0 MCP client (`src/lib.rs`) |
| `tauri-app/examples/mcp_client.rs` | The rmcp client alone, without a window |
| `electron-app/` | Electron 45.2.3 app: `main.js`, `preload.js`, the MCP client on `@modelcontextprotocol/sdk` 1.32.2 |
| `mcp-server/server.mjs` | A stdio MCP server with one tool, `query_rows`, that returns a payload as text |
| `bench/make-payloads.mjs` | Writes `payloads/rows-<n>mb.json`, the same bytes for both apps (fixed seed) |
| `bench/make-csv.mjs` | Writes `payloads/rows-<n>mb.csv`, the same rows as CSV, for the article's puzzle |
| `bench/run.py`, `bench/procmem.py` | The harness: launches, timing, memory per process (`proc_pid_rusage`) |
| `bench/mcp-sdk-client.mjs` | The TypeScript SDK client alone: default limit, raised limit, and a linear read buffer |
| `bench/report.py` | `runs/*.jsonl` → `runs/summary.json` |
| `bench/replicate.sh`, `bench/replication_table.py` | A second run on fresh builds, and the article's table comparing it with the first |
| `bench/charts.py`, `bench/tables.py` | The article's charts and IPC table from `runs/summary.json` |
| `bench/check_article.py` | Checks every number the article quotes against `runs/summary.json` |
| `runs/` | Every measurement, plus `runs/discarded/` with the runs of earlier, wrong versions of the harness |

## Run it

macOS only: the harness reads memory with `proc_pid_rusage` and finds WebKit's processes the way macOS
attributes them. You need Node 22 or later, Rust 1.90 or later, Python 3 and Xcode's command line tools.

```bash
./run.sh            # builds both apps, reruns every measurement (about an hour), checks the article
./run.sh report     # only recomputes runs/summary.json and checks the article
./play.sh 30        # one 30 MiB MCP tool result through both clients, with their default and raised limits
bench/replicate.sh  # in a clean copy: builds from scratch, repeats the headline numbers into runs/replication/
```

Keep the machine otherwise idle during `./run.sh`. The apps open windows; they quit on their own.

## Claims and where they are checked

| Claim in the article | Where it comes from |
| --- | --- |
| Idle footprint, all processes: Tauri 59.5 MiB, Electron 86.0 MiB; with an MCP client 58.8 and 102.7 MiB | `runs/startup.jsonl` (`bench/run.py startup`) |
| Script runs at 309 ms (Tauri) and 321 ms (Electron); WebKit's first frame stalled 8 to 80 s in 4 of 50 launches | `runs/startup-times.jsonl`, `runs/startup.jsonl` |
| 50 MiB to a parsed array: 112 ms (`ipc::Response`), 108 ms (Electron string), 279 ms (serde), 652 ms (Electron object) | `runs/ipc.jsonl` (`bench/run.py ipc`) |
| `Vec<u8>` arrives as an array of numbers: 1,080 ms and a 2,450 MiB page process at 50 MiB | `runs/ipc.jsonl`, method `vec-u8` |
| A `Channel` resolves `invoke()` before its chunks; waiting for them takes 948 ms | `ui/bridge-tauri.js` (`channel`), `runs/ipc.jsonl` |
| Without context isolation the Electron object route drops from 652 to 301 ms | `runs/ipc-no-isolation.jsonl` |
| With rows already held as structs, Tauri's default return (165 ms) beats serialising to bytes (190 ms); Electron object 567 ms vs `JSON.stringify` 144 ms | `runs/ipc-held.jsonl` (`bench/run.py held`) |
| Channel time does not depend on chunk size (64 KiB, 1 MiB, 8 MiB) | `runs/ipc-channel-chunks.jsonl` |
| A `Channel<&[u8]>` delivers JSON arrays of numbers (938 ms for 50 MiB); `Channel<Response>` delivers `ArrayBuffer`s (115 ms) | `runs/ipc-channel-raw.jsonl` (`bench/run.py channel-raw`) |
| A hidden Tauri window draws no first frame and reports `hidden`; Electron paints a hidden window | `runs/startup-hidden.jsonl` (`bench/run.py hidden`) |
| `invoke()` resolved with 0 chunks received in all 9 Channel calls | `runs/ipc-channel-resolve.jsonl` (`bench/run.py channel-resolve`) |
| Puzzle: 9 MiB of JSON closes the SDK session (10,600,460-byte line), 9 MiB of CSV passes (9,494,905) | `runs/mcp-csv.jsonl`, `runs/mcp-csv-wire.jsonl` (`bench/make-csv.mjs`) |
| The MCP limits count the escaped line: SDK passes 8 MiB of text, fails 9; rmcp passes 14, fails 15 | `runs/mcp-limits.jsonl`, `runs/mcp-limits-wire.jsonl` |
| TypeScript SDK: over 10 MiB the session closes; 50 MiB takes 6.3 s, 0.22 s with a linear buffer | `runs/mcp-sdk.jsonl` (`bench/mcp-sdk-client.mjs`) |
| rmcp: 50 MiB in 0.26 s; over 16 MiB the call is never answered | `runs/mcp-rmcp.jsonl` (`tauri-app/examples/mcp_client.rs`) |
| A 50 MiB tool result is a 56.1 MiB JSON-RPC line | `runs/mcp-wire-size.txt` |
| Every transfer delivered every row with the same checksum | asserted in `bench/check_article.py` |
| A second run on fresh builds repeats memory, start-up, every Tauri route and the MCP clients; Electron's fast routes moved (string 108 → 142 ms) | `runs/replication/` (`bench/replicate.sh`) |

`runs/milo-snapshot.json` is a single reading of a running copy of Milo, the author's Tauri app, which is not part
of this repository.

## Trademarks

TAURI is a trademark of The Tauri Programme within the Commons Conservancy. Electron is a trademark of the OpenJS
Foundation. This project is not affiliated with or endorsed by either.

## Author

Michał Woliński, [wolinski.com](https://wolinski.com).

## License

MIT, see [LICENSE](LICENSE).
