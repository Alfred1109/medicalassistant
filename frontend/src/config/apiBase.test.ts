import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { test } from 'node:test';
import axios from 'axios';
import { normalizeApiBaseUrl, resolveApiBaseUrl } from './apiBase.ts';

const cases: Array<[string | undefined, string]> = [
  [undefined, '/api'],
  ['', '/api'],
  ['  ', '/api'],
  ['/', '/api'],
  ['/api', '/api'],
  ['/api/', '/api'],
  ['/medical', '/medical/api'],
  ['/medical/', '/medical/api'],
  ['/medical/api/', '/medical/api'],
  ['http://localhost:5502', 'http://localhost:5502/api'],
  ['http://localhost:5502/', 'http://localhost:5502/api'],
  ['http://localhost:5502/api/', 'http://localhost:5502/api'],
  ['https://care.example/medical', 'https://care.example/medical/api'],
  ['https://care.example/medical/api/', 'https://care.example/medical/api'],
];

test('deployment prefix is used when no explicit API URL is configured', () => {
  assert.equal(resolveApiBaseUrl(undefined, '/medical'), '/medical/api');
  assert.equal(resolveApiBaseUrl(' ', '/medical/'), '/medical/api');
  assert.equal(resolveApiBaseUrl('https://api.example/base', '/medical'), 'https://api.example/base/api');
  assert.equal(resolveApiBaseUrl(undefined, undefined), '/api');
});

for (const [input, expected] of cases) {
  test(`API root ${JSON.stringify(input)} resolves to ${expected}`, () => {
    assert.equal(normalizeApiBaseUrl(input), expected);
    assert.equal(normalizeApiBaseUrl(expected), expected, 'normalization must be idempotent');
  });
}

for (const input of [
  'ftp://care.example',
  'ws://care.example',
  '//care.example/api',
  'care.example/api',
  'https://user:password@care.example/api',
  'https://care.example/api?token=secret',
  '/api?token=secret',
  '/api#fragment',
  '/medical\\api',
]) {
  test(`invalid API root ${JSON.stringify(input)} is rejected`, () => {
    assert.throws(() => normalizeApiBaseUrl(input));
  });
}

test('HTTP consumers use one /api prefix for origin and API-root configurations', async () => {
  const server = createServer((request, response) => {
    response.setHeader('Content-Type', 'application/json');
    if (!['/api/agents', '/medical/api/agents'].includes(request.url || '')) {
      response.statusCode = 404;
    }
    response.end(JSON.stringify({ path: request.url }));
  });
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  assert.ok(address && typeof address !== 'string');
  const origin = `http://127.0.0.1:${address.port}`;
  try {
    for (const [configured, expectedPath] of [
      [origin, '/api/agents'],
      [`${origin}/api/`, '/api/agents'],
      [`${origin}/medical`, '/medical/api/agents'],
      [`${origin}/medical/api/`, '/medical/api/agents'],
    ]) {
      const baseURL = normalizeApiBaseUrl(configured);
      const client = axios.create({ baseURL, proxy: false });
      const axiosResult = await client.get('/agents');
      assert.deepEqual(axiosResult.data, { path: expectedPath });
    }
    // Root-relative configuration resolves at the browser's current origin.
    const relativeUrl = new URL(`${normalizeApiBaseUrl()}/agents`, origin);
    const relativeResult = await fetch(relativeUrl);
    assert.equal(relativeResult.status, 200);
    assert.deepEqual(await relativeResult.json(), { path: '/api/agents' });
  } finally {
    await new Promise<void>((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
  }
});
