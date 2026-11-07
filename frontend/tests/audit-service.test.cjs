const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

// Exercise the real client at its HTTP boundary without importing browser auth state.
function clientFixture({ failure } = {}) {
  const calls = [];
  const payload = { total: 1, items: [{ id: 'fixture' }] };
  const api = {
    async get(url, config) {
      calls.push({ url, config });
      if (failure) throw failure;
      return { data: payload };
    },
  };
  const filename = path.resolve(__dirname, '../src/services/audit-service.ts');
  const compiled = ts.transpileModule(readFileSync(filename, 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, esModuleInterop: true },
  });
  const module = { exports: {} };
  vm.runInNewContext(compiled.outputText, {
    module, exports: module.exports, console: { error() {} },
    require(name) {
      assert.equal(name, './api', 'Only the existing HTTP boundary may be replaced');
      return api;
    },
  }, { filename });
  return { service: module.exports.AuditService, calls, payload };
}

test('list sends zero-based page offsets, exact date range and canonical list path', async () => {
  const { service, calls, payload } = clientFixture();
  const filters = {
    user_id: 'actor', action: 'grant', resource_type: 'permission', resource_id: 'target',
    status: 'success', start_date: '2026-11-29T16:00:00.000Z', end_date: '2026-11-30T15:59:59.999Z',
  };
  assert.equal(await service.getAuditLogs(filters, 3, 25, 'created_at', -1), payload);
  assert.equal(calls[0].url, 'audit-logs/');
  assert.equal(calls[0].config.params.skip, 75);
  assert.equal(calls[0].config.params.limit, 25);
  assert.equal(calls[0].config.params.sort_order, -1);
  for (const [key, value] of Object.entries(filters)) assert.equal(calls[0].config.params[key], value);
});

test('detail and recent URLs contain no double slash and encode resource identifiers', async () => {
  const { service, calls } = clientFixture();
  await service.getAuditLogById('507f1f77bcf86cd799439011');
  assert.equal(calls[0].url, 'audit-logs/507f1f77bcf86cd799439011');
  await service.getRecentLogsByUser('user/other?x=1', 20);
  assert.equal(calls[1].url, 'audit-logs/user/user%2Fother%3Fx%3D1/recent');
  assert.equal(calls[1].config.params.limit, 20);
});

test('invalid pagination or sorting fails before any HTTP request', async () => {
  const { service, calls } = clientFixture();
  for (const args of [[{}, -1, 10], [{}, 0, 101], [{}, 0, 1.5], [{}, NaN, 10],
    [{}, 0, 10, '$where', -1], [{}, 0, 10, 'created_at', 0]]) {
    await assert.rejects(service.getAuditLogs(...args), { name: 'RangeError' });
  }
  for (const limit of [0, 51, 1.5]) {
    await assert.rejects(service.getRecentLogsByUser('actor', limit), { name: 'RangeError' });
  }
  assert.equal(calls.length, 0);
});

test('HTTP failures propagate instead of returning simulated audit records', async () => {
  const failure = new Error('synthetic unavailable service');
  const { service } = clientFixture({ failure });
  await assert.rejects(service.getAuditLogs(), error => error === failure);
  await assert.rejects(service.getAuditLogById('507f1f77bcf86cd799439011'), error => error === failure);
  await assert.rejects(service.getRecentLogsByUser('actor'), error => error === failure);
});
