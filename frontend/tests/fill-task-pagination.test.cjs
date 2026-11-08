const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

function fixture(respond) {
  const calls = [];
  const filename = path.resolve(__dirname, '../src/services/formIntegrationService.ts');
  const compiled = ts.transpileModule(readFileSync(filename, 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, esModuleInterop: true },
  });
  const module = { exports: {} };
  vm.runInNewContext(compiled.outputText, {
    module, exports: module.exports, URL,
    require(name) {
      assert.equal(name, './apiClient');
      return { async get(url, config) {
        calls.push({ url, params: config.params });
        return respond(config.params, calls.length);
      } };
    },
  }, { filename });
  return { service: module.exports.formIntegrationService, calls };
}

test('later task pages send the selected status, offset and size to the real API client', async () => {
  const { service, calls } = fixture(({ skip, limit }) => ({
    items: Array.from({ length: limit }, (_, index) => ({ id: `task-${skip + index}` })),
    total: 81, skip, limit,
  }));
  const result = await service.listFillTaskPage({ status: 'waiting_fill', page: 2, pageSize: 20 });
  assert.equal(calls[0].url, '/integrations/forms/fill-tasks');
  assert.equal(calls[0].params.skip, 40);
  assert.equal(calls[0].params.limit, 20);
  assert.equal(calls[0].params.status, 'waiting_fill');
  assert.equal(result.items[0].id, 'task-40');
  assert.equal(result.page, 2);
});

test('shrinking results reload the last existing page, including further concurrent removal', async () => {
  const totals = [41, 19, 19];
  const { service, calls } = fixture(({ skip, limit }, count) => ({
    items: skip < totals[count - 1] ? [{ id: `task-${skip}` }] : [],
    total: totals[count - 1], skip, limit,
  }));
  const result = await service.listFillTaskPage({ status: 'waiting_fill', page: 4, pageSize: 20 });
  assert.deepEqual(calls.map(call => call.params.skip), [80, 40, 0]);
  assert.equal(result.page, 0);
  assert.equal(result.total, 19);
  assert.equal(result.items[0].id, 'task-0');
});

test('an empty filter resets the out-of-range page to zero without returning old tasks', async () => {
  const { service, calls } = fixture(({ skip, limit }) => ({ items: [], total: 0, skip, limit }));
  const result = await service.listFillTaskPage({ status: '', page: 2, pageSize: 50 });
  assert.deepEqual(calls.map(call => call.params.skip), [100, 0]);
  assert.equal('status' in calls[0].params, false);
  assert.equal(result.page, 0);
  assert.equal(result.items.length, 0);
});

test('HTTP failures propagate and invalid pages never issue a request', async () => {
  const failure = new Error('service unavailable');
  const { service, calls } = fixture(() => { throw failure; });
  for (const query of [
    { page: -1, pageSize: 20 }, { page: 1.5, pageSize: 20 },
    { page: 0, pageSize: 0 }, { page: 0, pageSize: 101 },
  ]) await assert.rejects(service.listFillTaskPage({ status: '', ...query }), { name: 'RangeError' });
  assert.equal(calls.length, 0);
  await assert.rejects(service.listFillTaskPage({ status: '', page: 0, pageSize: 20 }), error => error === failure);
});
