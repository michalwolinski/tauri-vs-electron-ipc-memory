// Writes payloads/rows-<n>mb.csv: the same rows as the JSON payloads, as CSV, cut at n MiB.
// It needs payloads/rows-50mb.json (bench/make-payloads.mjs).
import { readFileSync, writeFileSync } from 'node:fs';

const mb = Number(process.argv[2] ?? 9);
const dir = new URL('../payloads/', import.meta.url);
const rows = JSON.parse(readFileSync(new URL('rows-50mb.json', dir), 'utf8'));
const columns = ['id', 'customer', 'email', 'amount', 'currency', 'created_at', 'paid', 'tags', 'note'];
const lines = [columns.join(',')];
let size = lines[0].length;
for (const row of rows) {
  if (size >= mb * 1024 * 1024) break;
  const line = columns.map((c) => ('tags' === c ? row.tags.join(';') : String(row[c]))).join(',');
  lines.push(line);
  size += line.length + 1;
}
const csv = lines.join('\n');
writeFileSync(new URL(`rows-${mb}mb.csv`, dir), csv);
console.log(`rows-${mb}mb.csv ${csv.length} bytes, ${lines.length - 1} rows`);
