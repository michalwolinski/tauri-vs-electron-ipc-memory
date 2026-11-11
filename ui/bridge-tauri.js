// In Tauri, window.bridge is built from window.__TAURI__ (withGlobalTauri). Electron's preload sets it instead.
if (window.__TAURI__) {
  const { invoke, Channel } = window.__TAURI__.core;
  const decoder = new TextDecoder();

  window.bridge = {
    runtime: 'tauri',
    plan: () => invoke('plan'),
    mark: (name) => invoke('mark', { name }),
    ready: () => invoke('ready'),
    result: (r) => invoke('result', { r }),
    done: () => invoke('done'),
    // Each method returns { raw, rows }: raw is what arrived, rows the parsed array.
    methods: {
      // A typed Vec<Row> serialised by serde: the default way to return data.
      'serde-struct': async (mb) => {
        const rows = await invoke('rows_struct', { mb });
        return { arrived: performance.now(), rows };
      },
      // The JSON text returned as a Rust String: JSON inside a JSON string.
      'string': async (mb) => {
        const text = await invoke('rows_string', { mb });
        const arrived = performance.now();
        return { arrived, rows: JSON.parse(text) };
      },
      // Vec<u8> without ipc::Response: serde turns it into an array of numbers.
      'vec-u8': async (mb) => {
        const numbers = await invoke('rows_vec_u8', { mb });
        const arrived = performance.now();
        return { arrived, rows: JSON.parse(decoder.decode(new Uint8Array(numbers))) };
      },
      // tauri::ipc::Response: the bytes arrive as an ArrayBuffer.
      'raw-response': async (mb) => {
        const buffer = await invoke('rows_raw', { mb });
        const arrived = performance.now();
        return { arrived, rows: JSON.parse(decoder.decode(buffer)) };
      },
      // A Channel of &[u8] chunks (1 MiB unless BENCH_CHUNK_KIB says otherwise), and the same chunks as
      // ipc::Response. invoke() resolves before the chunks arrive, so the command returns the byte count
      // and the page waits for all of them.
      'channel': (mb) => channelRoute('rows_channel', mb),
      'channel-raw': (mb) => channelRoute('rows_channel_raw', mb),
      // A custom URI scheme read with fetch, like an HTTP response.
      'protocol': async (mb) => {
        const response = await fetch(protocolUrl(`rows/${mb}`));
        const text = await response.text();
        const arrived = performance.now();
        return { arrived, rows: JSON.parse(text) };
      },
      // The tool result of a real MCP call, passed on as an ipc::Response.
      'mcp-raw': async (mb) => {
        const buffer = await invoke('mcp_rows_raw', { mb });
        const arrived = performance.now();
        return { arrived, rows: JSON.parse(decoder.decode(buffer)) };
      },
      // The same tool result returned as a String.
      'mcp-string': async (mb) => {
        const text = await invoke('mcp_rows_string', { mb });
        const arrived = performance.now();
        return { arrived, rows: JSON.parse(text) };
      },
    },
  };

  async function channelRoute(command, mb) {
    const chunks = [];
    const types = new Set();
    let received = 0;
    let expected = Infinity;
    let finish;
    const complete = new Promise((resolve) => (finish = resolve));
    const channel = new Channel();
    channel.onmessage = (chunk) => {
      types.add(chunk instanceof ArrayBuffer ? 'ArrayBuffer' : Array.isArray(chunk) ? 'Array' : typeof chunk);
      const bytes = new Uint8Array(chunk);
      chunks.push(bytes);
      received += bytes.length;
      if (received === expected) finish();
    };
    expected = await invoke(command, { mb, onChunk: channel });
    const atResolve = chunks.length;
    if (received === expected) finish();
    await complete;
    const arrived = performance.now();
    const extra = { chunks_when_invoke_resolved: atResolve, chunks: chunks.length, chunk_types: [...types] };
    return { arrived, rows: JSON.parse(joinAndDecode(chunks)), extra };
  }

  // macOS and Linux serve custom schemes as bench://localhost, Windows as http://bench.localhost.
  function protocolUrl(path) {
    return navigator.userAgent.includes('Windows') ? `http://bench.localhost/${path}` : `bench://localhost/${path}`;
  }

  function joinAndDecode(chunks) {
    const total = chunks.reduce((n, c) => n + c.length, 0);
    const all = new Uint8Array(total);
    let offset = 0;
    for (const c of chunks) {
      all.set(c, offset);
      offset += c.length;
    }
    return decoder.decode(all);
  }
}
