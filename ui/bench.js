// Runs the plan the backend hands over and reports every timing back to it.
const log = (line) => (document.getElementById('log').textContent += line + '\n');
const status = (text) => (document.getElementById('status').textContent = text);

async function main() {
  // Two marks: the script ran, then the first frame after it (time to interactive). Each carries the
  // page's own clock, so a slow page start and a late first frame can be told apart.
  await window.bridge.mark(`script ${Math.round(performance.now())} ${document.visibilityState}`);
  await new Promise((resolve) => requestAnimationFrame(() => setTimeout(resolve, 0)));
  await window.bridge.mark(`frame ${Math.round(performance.now())} ${document.visibilityState}`);
  await window.bridge.ready();

  const plan = await window.bridge.plan();
  if (plan.mode !== 'ipc') {
    status(`${window.bridge.runtime} ready`);
    return;
  }

  const methods = window.bridge.methods ?? window.electronMethods;
  const method = methods[plan.method];
  if (undefined === method) {
    throw new Error(`unknown method ${plan.method}`);
  }
  for (let i = 0; i < plan.reps; i++) {
    status(`${plan.method} ${plan.mb} MB, run ${i + 1}`);
    const start = performance.now();
    const { arrived, rows, extra } = await method(plan.mb);
    const parsed = performance.now();
    // Touch the data the way a table view would, so nothing stays lazy.
    const total = rows.reduce((sum, row) => sum + row.amount, 0);
    const r = {
      runtime: window.bridge.runtime,
      method: plan.method,
      mb: plan.mb,
      run: i + 1,
      transfer_ms: arrived - start,
      parse_ms: parsed - arrived,
      total_ms: parsed - start,
      rows: rows.length,
      checksum: Math.round(total * 100),
      ...extra,
    };
    log(JSON.stringify(r));
    await window.bridge.result(r);
    await new Promise((resolve) => setTimeout(resolve, plan.pause_ms));
  }
  status('done');
  await window.bridge.done();
}

main().catch((e) => {
  status('error: ' + e);
  window.bridge.result({ error: String(e && e.stack ? e.stack : e) }).finally(() => window.bridge.done());
});
