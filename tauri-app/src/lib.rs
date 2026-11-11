// Tauri side of the bench: the same plan, payloads and MCP server as the Electron app.
use std::{
    borrow::Cow,
    env, fs,
    io::Write,
    path::PathBuf,
    process::Stdio,
    sync::{Arc, OnceLock},
};

use rmcp::{
    RoleClient, ServiceExt,
    model::CallToolRequestParams,
    service::RunningService,
    transport::async_rw::{AsyncRwTransport, DEFAULT_MAX_LINE_LENGTH},
};
use serde::{Deserialize, Serialize};
use tauri::{
    Manager, State,
    http::Response as HttpResponse,
    ipc::{Channel, Response},
};

#[derive(Clone, Serialize)]
struct Plan {
    mode: String,
    method: String,
    mb: u32,
    reps: u32,
    pause_ms: u32,
}

// One database-like row, the shape bench/make-payloads.mjs writes.
#[derive(Serialize, Deserialize)]
struct Row {
    id: u64,
    customer: String,
    email: String,
    amount: f64,
    currency: String,
    created_at: String,
    paid: bool,
    tags: Vec<String>,
    note: String,
}

struct Bench {
    plan: Plan,
    payload: Arc<Vec<u8>>,
    // The rows parsed once at start-up, for the routes that begin with data the backend already holds.
    held: Arc<Vec<Row>>,
    mcp: OnceLock<RunningService<RoleClient, ()>>,
}

fn var(name: &str, default: &str) -> String {
    env::var(name).unwrap_or_else(|_| default.to_string())
}

#[tauri::command]
fn plan(bench: State<'_, Bench>) -> Plan {
    bench.plan.clone()
}

#[tauri::command]
fn mark(name: String) {
    println!("MARK {name}");
}

#[tauri::command]
fn ready() {
    println!("READY");
}

#[tauri::command]
fn result(r: serde_json::Value) {
    let line = format!("{r}\n");
    match env::var("BENCH_OUT") {
        Ok(path) => fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(path)
            .and_then(|mut f| f.write_all(line.as_bytes()))
            .expect("BENCH_OUT is writable"),
        Err(_) => print!("{line}"),
    }
}

// The harness reads the memory of every process first, then quits the app itself.
#[tauri::command]
fn done() {
    println!("DONE");
}

#[tauri::command]
fn rows_struct(bench: State<'_, Bench>) -> Result<Vec<Row>, String> {
    serde_json::from_slice(&bench.payload).map_err(|e| e.to_string())
}

// Parses the whole result in Rust and sends only the rows a table shows first.
#[tauri::command]
fn rows_first_page(bench: State<'_, Bench>) -> Result<Response, String> {
    let rows: Vec<Row> = serde_json::from_slice(&bench.payload).map_err(|e| e.to_string())?;
    let page = &rows[..rows.len().min(100)];
    serde_json::to_vec(page)
        .map(Response::new)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn rows_string(bench: State<'_, Bench>) -> String {
    String::from_utf8_lossy(&bench.payload).into_owned()
}

#[tauri::command]
fn rows_vec_u8(bench: State<'_, Bench>) -> Vec<u8> {
    bench.payload.to_vec()
}

#[tauri::command]
fn rows_raw(bench: State<'_, Bench>) -> Response {
    Response::new(bench.payload.to_vec())
}

// Rows the backend already holds, returned the default way: serde writes the JSON.
#[tauri::command]
fn held_struct(bench: State<'_, Bench>) -> Arc<Vec<Row>> {
    bench.held.clone()
}

// The same rows, serialised by the command itself and returned as bytes.
#[tauri::command]
fn held_bytes(bench: State<'_, Bench>) -> Result<Response, String> {
    serde_json::to_vec(&*bench.held)
        .map(Response::new)
        .map_err(|e| e.to_string())
}

// Returns the byte count: the page cannot treat the resolved invoke() as "all chunks arrived".
#[tauri::command]
fn rows_channel(bench: State<'_, Bench>, on_chunk: Channel<&[u8]>) -> Result<usize, String> {
    let chunk_kib: usize = var("BENCH_CHUNK_KIB", "1024")
        .parse()
        .map_err(|_| "BENCH_CHUNK_KIB is a number")?;
    for chunk in bench.payload.chunks(chunk_kib * 1024) {
        on_chunk.send(chunk).map_err(|e| e.to_string())?;
    }
    Ok(bench.payload.len())
}

// The same chunks wrapped in ipc::Response: a Channel of &[u8] sends JSON arrays of numbers, because
// &[u8] implements Serialize; only Response takes the raw path.
#[tauri::command]
fn rows_channel_raw(bench: State<'_, Bench>, on_chunk: Channel<Response>) -> Result<usize, String> {
    for chunk in bench.payload.chunks(1024 * 1024) {
        on_chunk
            .send(Response::new(chunk.to_vec()))
            .map_err(|e| e.to_string())?;
    }
    Ok(bench.payload.len())
}

async fn mcp_text(bench: &Bench, mb: u32) -> Result<String, String> {
    let client = bench.mcp.get().ok_or("MCP is not connected")?;
    let mut arguments = serde_json::Map::new();
    arguments.insert("mb".into(), mb.into());
    let params = CallToolRequestParams::new(Cow::Borrowed("query_rows")).with_arguments(arguments);
    let mut result = client.call_tool(params).await.map_err(|e| e.to_string())?;
    let first = result.content.drain(..).next().ok_or("empty tool result")?;
    first
        .as_text()
        .map(|t| t.text.clone())
        .ok_or_else(|| "not text".to_string())
}

#[tauri::command]
async fn mcp_rows_raw(bench: State<'_, Bench>, mb: u32) -> Result<Response, String> {
    Ok(Response::new(mcp_text(&bench, mb).await?.into_bytes()))
}

#[tauri::command]
async fn mcp_rows_string(bench: State<'_, Bench>, mb: u32) -> Result<String, String> {
    mcp_text(&bench, mb).await
}

// TokioChildProcess has no line-limit setting, so the child is spawned here and its pipes wrapped.
// rmcp drops any line over DEFAULT_MAX_LINE_LENGTH (16 MiB); MCP_MAX_BUFFER=default keeps that limit.
async fn connect_mcp(server: String) -> RunningService<RoleClient, ()> {
    let mut child = tokio::process::Command::new(var("MCP_NODE", "node"))
        .arg(server)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .kill_on_drop(true)
        .spawn()
        .expect("MCP server starts");
    let stdout = child.stdout.take().expect("stdout is piped");
    let stdin = child.stdin.take().expect("stdin is piped");
    let limit = match var("MCP_MAX_BUFFER", "").as_str() {
        "default" => DEFAULT_MAX_LINE_LENGTH,
        _ => 256 * 1024 * 1024,
    };
    let transport = AsyncRwTransport::new_client(stdout, stdin).with_max_line_length(limit);
    // The child lives as long as the app; dropping it would kill the server.
    Box::leak(Box::new(child));
    ().serve(transport).await.expect("MCP handshake")
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let bench_plan = Plan {
        mode: var("BENCH_MODE", "startup"),
        method: var("BENCH_METHOD", ""),
        mb: var("BENCH_MB", "1").parse().expect("BENCH_MB is a number"),
        reps: var("BENCH_REPS", "5")
            .parse()
            .expect("BENCH_REPS is a number"),
        pause_ms: var("BENCH_PAUSE_MS", "500")
            .parse()
            .expect("BENCH_PAUSE_MS is a number"),
    };
    let payload = match bench_plan.mode.as_str() {
        "ipc" => {
            let dir = PathBuf::from(var(
                "BENCH_PAYLOADS",
                concat!(env!("CARGO_MANIFEST_DIR"), "/../payloads"),
            ));
            fs::read(dir.join(format!("rows-{}mb.json", bench_plan.mb)))
                .expect("payload file exists")
        }
        _ => Vec::new(),
    };
    let held: Vec<Row> = match bench_plan.method.starts_with("held-") {
        true => serde_json::from_slice(&payload).expect("payload is valid JSON"),
        false => Vec::new(),
    };
    let wants_mcp = "1" == var("MCP", "") || bench_plan.method.starts_with("mcp-");

    tauri::Builder::default()
        .manage(Bench {
            plan: bench_plan,
            payload: Arc::new(payload),
            held: Arc::new(held),
            mcp: OnceLock::new(),
        })
        .register_asynchronous_uri_scheme_protocol("bench", |ctx, _request, responder| {
            let payload = ctx.app_handle().state::<Bench>().payload.clone();
            std::thread::spawn(move || {
                responder.respond(
                    HttpResponse::builder()
                        .header("content-type", "application/json")
                        .header("access-control-allow-origin", "*")
                        .body(payload.to_vec())
                        .expect("valid response"),
                )
            });
        })
        .setup(move |app| {
            // BENCH_HIDDEN=1 hides the window, to test whether WebKit draws a first frame for it.
            if "1" == var("BENCH_HIDDEN", "")
                && let Some(window) = app.get_webview_window("main")
            {
                window.hide()?;
            }
            if wants_mcp {
                let server = env::var("MCP_SERVER").expect("MCP_SERVER is set");
                let client = tauri::async_runtime::block_on(connect_mcp(server));
                let _ = app.state::<Bench>().mcp.set(client);
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            plan,
            mark,
            ready,
            result,
            done,
            rows_struct,
            rows_first_page,
            held_struct,
            held_bytes,
            rows_string,
            rows_vec_u8,
            rows_raw,
            rows_channel,
            rows_channel_raw,
            mcp_rows_raw,
            mcp_rows_string
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
