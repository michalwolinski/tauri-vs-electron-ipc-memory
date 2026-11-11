// The TypeScript SDK's stdio client alone, no Electron: time per tool call at each size, with the default
// 10 MiB buffer, with a raised one, and with a ReadBuffer that does not re-copy and re-scan on every chunk.
//
// node bench/mcp-sdk-client.mjs default|raised|linear [MiB] [json|csv]   (without a size: 1, 10, 50 and 1 again)
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(new URL('../electron-app/package.json', import.meta.url));
const sdk = (path) => import(require.resolve(`@modelcontextprotocol/sdk/${path}`));
const { Client } = await sdk('client/index.js');
const { StdioClientTransport } = await sdk('client/stdio.js');
const { ReadBuffer, deserializeMessage } = await sdk('shared/stdio.js');

const mode = process.argv[2] ?? 'default';
if ('linear' === mode) {
  // Keep the chunks in a list and search only the new chunk for the newline.
  ReadBuffer.prototype.append = function (chunk) {
    (this._chunks ??= []).push(chunk);
    this._size = (this._size ?? 0) + chunk.length;
    if (this._size > this._maxBufferSize) {
      this.clear();
      throw new Error(`ReadBuffer exceeded maximum size of ${this._maxBufferSize} bytes`);
    }
    if (chunk.includes(0x0a)) {
      this._buffer = Buffer.concat([...(this._buffer ? [this._buffer] : []), ...this._chunks]);
      this._chunks = [];
      this._size = this._buffer.length;
    }
  };
  ReadBuffer.prototype.readMessage = function () {
    const index = this._buffer?.indexOf(0x0a) ?? -1;
    if (-1 === index) {
      return null;
    }
    const line = this._buffer.toString('utf8', 0, index).replace(/\r$/, '');
    this._buffer = this._buffer.subarray(index + 1);
    this._size = this._buffer.length + (this._chunks?.reduce((n, c) => n + c.length, 0) ?? 0);
    return deserializeMessage(line);
  };
}

const server = fileURLToPath(new URL('../mcp-server/server.mjs', import.meta.url));
const transport = new StdioClientTransport({
  command: 'node',
  args: [server],
  ...('default' === mode ? {} : { maxBufferSize: 256 * 1024 * 1024 }),
});
const client = new Client({ name: 'sdk-bench', version: '1.0.0' });
let closed = false;
client.onclose = () => (closed = true);
await client.connect(transport);
const pid = transport.pid;

const format = process.argv[4] ?? 'json';
const sizes = process.argv[3] ? [Number(process.argv[3])] : [1, 10, 50, 1];
for (const mb of sizes) {
  const started = performance.now();
  try {
    const result = await client.callTool({ name: 'query_rows', arguments: { mb, format } });
    const ms = performance.now() - started;
    console.log(JSON.stringify({ mode, format, mb, ms: Math.round(ms * 10) / 10, text_bytes: result.content[0].text.length }));
  } catch (e) {
    const ms = performance.now() - started;
    console.log(JSON.stringify({ mode, format, mb, ms: Math.round(ms * 10) / 10, error: e.message }));
  }
}
let alive = true;
try {
  process.kill(pid, 0);
} catch {
  alive = false;
}
console.log(JSON.stringify({ mode, server_alive: alive, client_closed: closed }));
await client.close().catch(() => {});
