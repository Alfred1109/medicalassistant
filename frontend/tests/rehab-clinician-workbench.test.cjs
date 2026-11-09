const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { buildSync, transformSync } = require('esbuild');
const root = path.resolve(__dirname, '..');
const utilities = buildSync({ entryPoints: [path.join(root, 'src/utils/rehabClinicalWorkbench.ts')],
  bundle: true, platform: 'node', format: 'cjs', write: false }).outputFiles[0].text;
const loaded = { exports: {} };
vm.runInNewContext(utilities, { module: loaded, exports: loaded.exports, require, Date, crypto, Uint8Array });
const domain = loaded.exports;

test('draft content requires explicit clinical inputs and preserves local time precisely', () => {
  const empty = domain.emptyContent();
  assert.equal(Object.values(empty).every(value => value === ''), true);
  assert.throws(() => domain.contentPayload(empty), /请填写/);
  const source = { name: ' 手工方案 ', description: ' 医护输入 ', goal: ' 明确目标 ', start_date: '2026-11-09T03:04:05.678Z' };
  const result = domain.contentPayload(domain.contentForm(source));
  assert.equal(result.start_date, source.start_date);
  assert.equal(result.name, '手工方案');
  assert.equal(result.patient_instructions, null);
  assert.throws(() => domain.contentPayload({ ...domain.contentForm(source), end_date: '2020-01-01T00:00' }), /开始和结束/);
});

test('editing existing interventions preserves exact identities and detailed clinician fields', () => {
  const source = { item_id: 'a'.repeat(24), intervention_type: 'medication', name: ' 已核实条目 ',
    medication_fields: { drug_ref: 'original', dosage: { value: 2, unit: 'explicit' } },
    contraindications: ['人工填写'], schedule: { frequency: '医护安排' } };
  const [result] = domain.validateItems([source]);
  assert.equal(result.item_id, source.item_id);
  assert.equal(result.medication_fields, source.medication_fields);
  assert.equal(result.name, '已核实条目');
  assert.throws(() => domain.validateItems([{ ...source, name: ' ' }]), /名称/);
});

test('operation identity works without randomUUID and conflicts require fresh review', () => {
  const one = domain.operationId(), two = domain.operationId();
  assert.match(one, /^[0-9a-f]{32}$/);
  assert.notEqual(one, two);
  assert.match(domain.workbenchError({ response: { status: 409 } }, 'fallback'), /重新加载核对/);
  assert.match(domain.workbenchError({ response: { status: 403 } }, 'fallback'), /无权/);
});

test('clinical transport sends scoped reads, CAS and explicit withdrawal action', async () => {
  const calls = [];
  const transport = Object.fromEntries(['get', 'post', 'put'].map(method => [method, async (...args) => {
    calls.push({ method, args }); return { data: {} };
  }]));
  const code = transformSync(fs.readFileSync(path.join(root, 'src/services/rehabClinicalWorkbench.ts'), 'utf8'), { loader: 'ts', format: 'cjs' }).code;
  const module = { exports: {} };
  vm.runInNewContext(code, { module, exports: module.exports, require: () => transport, encodeURIComponent });
  const api = module.exports.rehabClinicalWorkbench;
  await api.plans('patient', 20, 20, 'signal');
  assert.equal(calls[0].args[1].params.patient_id, 'patient');
  assert.equal(calls[0].args[1].params.skip, 20);
  await api.create('patient', { name: 'manual', description: 'manual', goal: 'manual', start_date: '2026-01-01T00:00:00Z' });
  assert.equal(calls[1].args[1].status, 'draft');
  assert.equal(calls[1].args[1].patient_id, 'patient');
  await api.publish('plan', { request_id: 'same-request', draft_id: 'draft', expected_draft_revision: 2,
    expected_publication_id: 'prior', confirmed: true, confirmation_note: 'reviewed' });
  assert.equal(calls[2].args[1].expected_publication_id, 'prior');
  await api.withdraw('plan', { request_id: 'withdraw', expected_publication_id: 'prior', action: 'archive', reason: 'manual' });
  assert.equal(calls[3].args[1].action, 'archive');
});
