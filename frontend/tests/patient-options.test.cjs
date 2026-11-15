const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const { transformSync } = require('esbuild');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

function fixture(data, failure) {
  const file = path.resolve(__dirname, '../src/hooks/usePatientOptions.ts');
  const loaded = new Module(file, module);
  const calls = [];
  let resource;
  loaded.require = name => {
    if (name === 'react') return { useCallback: callback => callback };
    if (name === '../services/httpClient') return { get: async (...args) => {
      calls.push(args);
      if (failure) throw failure;
      return { data };
    } };
    if (name === './useAsyncResource') return { useAsyncResource: (load, enabled) => {
      resource = { load, enabled };
      return { data: null, loading: enabled, error: null };
    } };
    throw new Error(`Unexpected dependency: ${name}`);
  };
  loaded._compile(transformSync(fs.readFileSync(file, 'utf8'), { loader: 'ts', format: 'cjs' }).code, file);
  return { use: (...args) => { const result = loaded.exports.usePatientOptions(...args); return { ...resource, result }; }, calls };
}

test('each care role uses its own authorized directory and passes request cancellation', async () => {
  for (const [role, endpoint] of [['doctor', '/doctors/patients'], ['health_manager', '/health-managers/patients']]) {
    const f = fixture([{ id: 'one', name: '甲' }, { id: 'one', name: '重复' }, { _id: 'two' }, {}]);
    const resource = f.use(role, 'actor-one');
    assert.equal(resource.enabled, true);
    const signal = new AbortController().signal;
    assert.deepEqual(await resource.load(signal), [{ id: 'one', name: '甲' }, { id: 'two', name: '未命名患者' }]);
    assert.deepEqual(f.calls, [[endpoint, { signal }]]);
  }
});

test('non-medical and absent identities never enable a directory request', () => {
  const f = fixture([]);
  for (const [role, id] of [['patient', 'patient-one'], ['admin', 'admin-one'], ['doctor', undefined], [undefined, undefined]]) {
    assert.equal(f.use(role, id).enabled, false);
  }
  assert.deepEqual(f.calls, []);
});

test('directory failures remain visible and invalid payloads never become a successful empty scope', async () => {
  const failure = { response: { status: 503, data: { error: 'PATIENT_DOMAIN_STATE_UNAVAILABLE' } } };
  await assert.rejects(fixture(null, failure).use('doctor', 'actor').load(new AbortController().signal), error => error === failure);
  await assert.rejects(fixture({ patients: [] }).use('doctor', 'actor').load(new AbortController().signal), /响应格式无效/);
});

test('shared options preserve diagnosis and demographic labels without changing patient identifiers', async () => {
  const f = fixture([{ id: 'one', name: '甲', diagnosis: '随访诊断', age: 42, gender: '女' },
    { id: 'two', name: '乙', diagnosis: null, age: 'unknown', gender: null }]);
  const options = await f.use('health_manager', 'actor').load(new AbortController().signal);
  assert.deepEqual(options, [{ id: 'one', name: '甲', diagnosis: '随访诊断', age: 42, gender: '女' },
    { id: 'two', name: '乙' }]);
});

test('shared patient selector preserves all-patient sentinel, loading and direct-link selections', () => {
  const file = path.resolve(__dirname, '../src/components/common/PatientSelect.tsx');
  const loaded = new Module(file, module); loaded.filename = file;
  loaded.paths = Module._nodeModulePaths(__dirname);
  loaded._compile(transformSync(fs.readFileSync(file, 'utf8'), { loader: 'tsx', format: 'cjs' }).code, file);
  const render = props => renderToStaticMarkup(React.createElement(loaded.exports.default,
    { label: '患者范围', patients: [], onChange: () => {}, ...props }));
  const all = render({ value: 'all', emptyValue: 'all', emptyLabel: '全部患者' });
  assert.ok(all.includes('全部患者'));
  assert.equal(all.includes('>all<'), false);
  assert.ok(render({ value: 'all', emptyValue: 'all', loading: true }).includes('aria-disabled="true"'));
  assert.ok(render({ value: 'linked-patient-id' }).includes('linked-patient-id'));
  assert.ok(render({ value: 'one', patients: [{ id: 'one', name: '甲（随访诊断）' }] }).includes('甲（随访诊断）'));
});
