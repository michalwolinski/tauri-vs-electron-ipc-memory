// Exposes the same window.bridge the Tauri page builds from window.__TAURI__. With context isolation
// on (the default), contextBridge copies every value it hands to the page.
const { contextBridge, ipcRenderer } = require('electron');

const call = (channel, ...args) => ipcRenderer.invoke(channel, ...args);

const expose = (name, api) =>
  process.contextIsolated ? contextBridge.exposeInMainWorld(name, api) : (window[name] = api);

expose('bridge', {
  runtime: 'electron',
  plan: () => call('plan'),
  mark: (name) => call('mark', name),
  ready: () => call('ready'),
  result: (r) => call('result', r),
  done: () => call('done'),
});

// Methods run in the page's world, so the parse happens there and not in the preload.
expose('electronIpc', {
  object: (mb) => call('rows:object', mb),
  firstPage: (mb) => call('rows:first-page', mb),
  heldObject: (mb) => call('held:object', mb),
  heldString: (mb) => call('held:string', mb),
  string: (mb) => call('rows:string', mb),
  buffer: (mb) => call('rows:buffer', mb),
  mcpString: (mb) => call('mcp:string', mb),
  mcpObject: (mb) => call('mcp:object', mb),
});
