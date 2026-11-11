// In Electron the preload exposes window.electronIpc; the parse runs here, in the page's own world.
if (window.electronIpc) {
  const ipc = window.electronIpc;
  const decoder = new TextDecoder();

  window.electronMethods = {
    // The main process parses and returns the object: structured clone over IPC.
    'object': async (mb) => {
      const rows = await ipc.object(mb);
      return { arrived: performance.now(), rows };
    },
    'string': async (mb) => {
      const text = await ipc.string(mb);
      const arrived = performance.now();
      return { arrived, rows: JSON.parse(text) };
    },
    // A Node Buffer arrives as a Uint8Array.
    'buffer': async (mb) => {
      const bytes = await ipc.buffer(mb);
      const arrived = performance.now();
      return { arrived, rows: JSON.parse(decoder.decode(bytes)) };
    },
    // Rows the main process already holds, returned as an object.
    'held-object': async (mb) => {
      const rows = await ipc.heldObject(mb);
      return { arrived: performance.now(), rows };
    },
    // The same rows, stringified in the main process and parsed in the page.
    'held-string': async (mb) => {
      const text = await ipc.heldString(mb);
      const arrived = performance.now();
      return { arrived, rows: JSON.parse(text) };
    },
    // The main process parses everything and sends only the first 100 rows.
    'first-page': async (mb) => {
      const rows = await ipc.firstPage(mb);
      return { arrived: performance.now(), rows };
    },
    // protocol.handle, read with fetch.
    'protocol': async (mb) => {
      const response = await fetch(`bench://localhost/rows/${mb}`);
      const text = await response.text();
      const arrived = performance.now();
      return { arrived, rows: JSON.parse(text) };
    },
    'mcp-string': async (mb) => {
      const text = await ipc.mcpString(mb);
      const arrived = performance.now();
      return { arrived, rows: JSON.parse(text) };
    },
    'mcp-object': async (mb) => {
      const rows = await ipc.mcpObject(mb);
      return { arrived: performance.now(), rows };
    },
  };
}
