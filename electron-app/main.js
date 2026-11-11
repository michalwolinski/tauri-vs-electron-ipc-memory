// Electron side of the bench: the same plan, payloads and MCP server as the Tauri app.
const { app, BrowserWindow, ipcMain, protocol } = require('electron');
const { appendFileSync, readFileSync } = require('node:fs');
const path = require('node:path');

const env = process.env;
const plan = {
  mode: env.BENCH_MODE ?? 'startup',
  method: env.BENCH_METHOD ?? '',
  mb: Number(env.BENCH_MB ?? 1),
  reps: Number(env.BENCH_REPS ?? 5),
  pause_ms: Number(env.BENCH_PAUSE_MS ?? 500),
};
const payloadDir = env.BENCH_PAYLOADS ?? path.join(__dirname, '..', 'payloads');
const payload = 'ipc' === plan.mode ? readFileSync(path.join(payloadDir, `rows-${plan.mb}mb.json`)) : null;
// The rows parsed once at start-up, for the routes that begin with data the main process already holds.
const held = plan.method.startsWith('held-') ? JSON.parse(payload.toString('utf8')) : null;
let mcp = null;

protocol.registerSchemesAsPrivileged([{ scheme: 'bench', privileges: { standard: true, supportFetchAPI: true, corsEnabled: true } }]);

async function connectMcp() {
  const { Client } = await import('@modelcontextprotocol/sdk/client/index.js');
  const { StdioClientTransport } = await import('@modelcontextprotocol/sdk/client/stdio.js');
  const client = new Client({ name: 'electron-bench', version: '1.0.0' });
  // Over 10 MiB in one message (STDIO_DEFAULT_MAX_BUFFER_SIZE), the SDK's stdio client closes the
  // connection and stops the server; the caller only sees "Connection closed". MCP_MAX_BUFFER=default
  // keeps that limit to show it.
  const transport = new StdioClientTransport({
    command: env.MCP_NODE ?? 'node',
    args: [env.MCP_SERVER],
    ...('default' === env.MCP_MAX_BUFFER ? {} : { maxBufferSize: 256 * 1024 * 1024 }),
  });
  await client.connect(transport);
  return client;
}

async function mcpText(mb) {
  const result = await mcp.callTool({ name: 'query_rows', arguments: { mb } });
  return result.content[0].text;
}

ipcMain.handle('plan', () => plan);
ipcMain.handle('mark', (_e, name) => console.log(`MARK ${name}`));
ipcMain.handle('ready', () => console.log('READY'));
ipcMain.handle('result', (_e, r) => appendFileSync(env.BENCH_OUT ?? '/dev/stdout', JSON.stringify(r) + '\n'));
ipcMain.handle('done', () => console.log('DONE'));

ipcMain.handle('rows:object', () => JSON.parse(payload.toString('utf8')));
ipcMain.handle('rows:first-page', () => JSON.parse(payload.toString('utf8')).slice(0, 100));
ipcMain.handle('held:object', () => held);
ipcMain.handle('held:string', () => JSON.stringify(held));
ipcMain.handle('rows:string', () => payload.toString('utf8'));
ipcMain.handle('rows:buffer', () => payload);
ipcMain.handle('mcp:string', (_e, mb) => mcpText(mb));
ipcMain.handle('mcp:object', async (_e, mb) => JSON.parse(await mcpText(mb)));

app.whenReady().then(async () => {
  protocol.handle('bench', () => new Response(payload, { headers: { 'content-type': 'application/json', 'access-control-allow-origin': '*' } }));
  if ('1' === env.MCP || plan.method.startsWith('mcp-')) {
    mcp = await connectMcp();
  }
  const win = new BrowserWindow({
    width: 1000,
    height: 700,
    // BENCH_HIDDEN=1 hides the window, to test whether Chromium draws a first frame for it.
    show: '1' !== env.BENCH_HIDDEN,
    // BENCH_NO_ISOLATION=1 turns context isolation off (not for real apps) to show what contextBridge copies.
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: '1' !== env.BENCH_NO_ISOLATION,
      sandbox: '1' !== env.BENCH_NO_ISOLATION,
    },
  });
  win.loadFile(path.join(__dirname, 'ui', 'index.html'));
});

app.on('window-all-closed', () => app.quit());
