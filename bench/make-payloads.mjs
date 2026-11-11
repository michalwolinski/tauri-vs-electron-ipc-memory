// Writes payloads/rows-<n>mb.json: a JSON array of database-like rows, the same bytes for every app.
import { mkdirSync, writeFileSync } from 'node:fs';

const sizes = (process.argv[2] ?? '1,10,50').split(',').map(Number);
const dir = new URL('../payloads/', import.meta.url);
mkdirSync(dir, { recursive: true });

let seed = 20261110;
const next = () => (seed = (seed * 1103515245 + 12345) % 2147483648);
const words = ['invoice', 'refund', 'priority', 'eu', 'us', 'trial', 'annual', 'churn', 'vip', 'late'];

function row(id) {
  const tags = [words[next() % 10], words[next() % 10]];
  return {
    id,
    customer: `Customer ${next() % 100000}`,
    email: `user${next() % 1000000}@example.com`,
    amount: (next() % 1000000) / 100,
    currency: ['EUR', 'USD', 'PLN'][next() % 3],
    created_at: new Date(1700000000000 + (next() % 31536000) * 1000).toISOString(),
    paid: next() % 2 === 0,
    tags,
    note: 'Order note: ' + 'lorem ipsum dolor sit amet '.repeat(1 + (next() % 3)).trim(),
  };
}

for (const mb of sizes) {
  seed = 20261110;
  const target = mb * 1024 * 1024;
  const parts = [];
  let size = 2;
  for (let id = 1; size < target; id++) {
    const s = JSON.stringify(row(id));
    parts.push(s);
    size += s.length + 1;
  }
  const json = '[' + parts.join(',') + ']';
  writeFileSync(new URL(`rows-${mb}mb.json`, dir), json);
  console.log(`rows-${mb}mb.json ${json.length} bytes, ${parts.length} rows`);
}
