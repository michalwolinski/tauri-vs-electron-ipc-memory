// A stdio MCP server with one tool that returns a database-like result as text: payloads/rows-<mb>mb.json,
// or the .csv file of that size when format is "csv".
import { readFileSync } from 'node:fs';
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { z } from 'zod';

const payloads = new URL('../payloads/', import.meta.url);
const server = new McpServer({ name: 'rows', version: '1.0.0' });

server.registerTool(
  'query_rows',
  {
    description: 'Returns rows from the orders table as a JSON array, or as CSV.',
    inputSchema: { mb: z.number().int(), format: z.enum(['json', 'csv']).optional() },
  },
  async ({ mb, format = 'json' }) => ({
    content: [{ type: 'text', text: readFileSync(new URL(`rows-${mb}mb.${format}`, payloads), 'utf8') }],
  }),
);

await server.connect(new StdioServerTransport());
