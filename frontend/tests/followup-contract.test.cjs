const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const Module = require('node:module');
const path = require('node:path');
const { buildSync } = require('esbuild');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

const filename = path.resolve(__dirname, '.followup-contract.compiled.cjs');
const compiled = buildSync({
  stdin: { contents: `export * from './constants/followup'; export {default as FollowUpList} from './components/HealthManager/FollowUpList';`, resolveDir: path.resolve(__dirname, '../src'), loader: 'ts' },
  bundle: true, platform: 'node', format: 'cjs', write: false,
  packages: 'external', logLevel: 'silent',
}).outputFiles[0].text;
const loaded = new Module(filename, module);
loaded.filename = filename;
loaded.paths = Module._nodeModulePaths(__dirname);
const originalRequire = loaded.require.bind(loaded);
// Node CJS default interop differs from Vite for MUI's per-icon entrypoints.
loaded.require = name => {
  const result = originalRequire(name);
  return name.startsWith('@mui/icons-material/') ? result.default : result;
};
loaded._compile(compiled, filename);
const domain = loaded.exports;

function backendValues(enumName) {
  const schema = readFileSync(path.resolve(__dirname, '../../backend/app/schemas/followup.py'), 'utf8');
  const body = schema.match(new RegExp(`class ${enumName}\\(str, Enum\\):([\\s\\S]*?)(?=\\nclass )`))[1];
  return [...body.matchAll(/^\s+[A-Z_]+\s*=\s*"([^"]+)"/gm)].map(match => match[1]);
}

const record = {
  id: 'visit-1', patient_id: 'patient-1', provider_id: 'doctor-1', created_by: 'doctor-1',
  follow_up_type: 'phone', scheduled_date: '2000-01-01T00:00:00Z', status: 'scheduled',
  description: '随访', created_at: '2000-01-01T00:00:00Z', updated_at: '2000-01-01T00:00:00Z',
};
function render(status) {
  return renderToStaticMarkup(React.createElement(domain.FollowUpList, {
    records: [{ ...record, status }], totalCount: 1,
    onComplete() {}, onEdit() {}, onCancel() {}, onReschedule() {},
  }));
}

test('shared follow-up filter metadata covers each actual backend status and type exactly once', () => {
  for (const [options, name] of [[domain.followUpStatuses, 'FollowUpStatus'], [domain.followUpTypes, 'FollowUpType']]) {
    const values = options.map(item => item.value);
    assert.deepEqual([...values].sort(), backendValues(name).sort());
    assert.equal(new Set(values).size, values.length);
  }
});

test('list renders all server states and preserves unknown states without inventing a transition', () => {
  for (const state of domain.followUpStatuses) assert.ok(render(state.value).includes(state.label), state.value);
  const unknown = render('future_server_state');
  assert.ok(unknown.includes('future_server_state'));
  for (const status of ['in_review', 'completed', 'canceled', 'lost', 'future_server_state']) {
    assert.equal(render(status).includes(`title="${domain.manualEntryText.action}"`), false, status);
  }
});

test('elapsed scheduled date does not locally mark missed or lost; manual entry promises review', () => {
  const html = render('scheduled');
  assert.ok(html.includes('已计划'));
  for (const status of ['已错过', '已失访', '已逾期', '标记为已完成']) assert.equal(html.includes(status), false, status);
  assert.ok(html.includes(`title="${domain.manualEntryText.action}"`));
  assert.ok(domain.manualEntryText.confirmation.includes('审阅通过后才算完成'));
  assert.ok(domain.manualEntryText.success.includes('待医护审阅'));
});
