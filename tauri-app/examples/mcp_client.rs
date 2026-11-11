// The rmcp client alone, no webview: how long a tool call takes at each size, and what the default
// 16 MiB line limit does to a bigger result.
//
// cargo run --release --example mcp_client -- ../mcp-server/server.mjs [default|raised] [MiB]
// Without a size it calls 1, 10, 50 and 1 MiB again.
use std::{
    borrow::Cow,
    env,
    process::Stdio,
    time::{Duration, Instant},
};

use rmcp::{
    ServiceExt,
    model::CallToolRequestParams,
    transport::async_rw::{AsyncRwTransport, DEFAULT_MAX_LINE_LENGTH},
};

#[tokio::main]
async fn main() {
    let args: Vec<String> = env::args().collect();
    let mode = args.get(2).map(String::as_str).unwrap_or("raised");
    let limit = match mode {
        "default" => DEFAULT_MAX_LINE_LENGTH,
        _ => 256 * 1024 * 1024,
    };
    let mut child = tokio::process::Command::new("node")
        .arg(&args[1])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .kill_on_drop(true)
        .spawn()
        .expect("MCP server starts");
    let transport =
        AsyncRwTransport::new_client(child.stdout.take().unwrap(), child.stdin.take().unwrap())
            .with_max_line_length(limit);
    let client = ().serve(transport).await.expect("MCP handshake");

    let sizes: Vec<u64> = match args.get(3) {
        Some(mb) => vec![mb.parse().expect("size in MiB")],
        None => vec![1, 10, 50, 1],
    };
    for mb in sizes {
        let mut arguments = serde_json::Map::new();
        arguments.insert("mb".into(), mb.into());
        let params =
            CallToolRequestParams::new(Cow::Borrowed("query_rows")).with_arguments(arguments);
        let started = Instant::now();
        let outcome = tokio::time::timeout(Duration::from_secs(30), client.call_tool(params)).await;
        let ms = started.elapsed().as_secs_f64() * 1000.0;
        match outcome {
            Ok(Ok(result)) => {
                let text = result.content[0]
                    .as_text()
                    .map(|t| t.text.len())
                    .unwrap_or(0);
                println!(
                    "{{\"mode\":\"{mode}\",\"mb\":{mb},\"ms\":{ms:.1},\"text_bytes\":{text}}}"
                );
            }
            Ok(Err(e)) => println!(
                "{{\"mode\":\"{mode}\",\"mb\":{mb},\"ms\":{ms:.1},\"error\":{:?}}}",
                e.to_string()
            ),
            Err(_) => println!(
                "{{\"mode\":\"{mode}\",\"mb\":{mb},\"ms\":{ms:.1},\"error\":\"no answer in 30 s\"}}"
            ),
        }
    }
    println!(
        "{{\"mode\":\"{mode}\",\"server_alive\":{}}}",
        child.try_wait().map(|s| s.is_none()).unwrap_or(false)
    );
}
