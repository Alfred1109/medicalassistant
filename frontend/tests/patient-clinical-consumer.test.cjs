const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const Module = require('node:module');
const { buildSync } = require('esbuild');
const root = path.resolve(__dirname, '..');

const define = {
  'import.meta.env.VITE_API_URL': 'undefined',
  'import.meta.env.VITE_API_PREFIX': 'undefined',
};

function compilePage(from, exportNames) {
  const compiled = buildSync({
    stdin: { contents: `export { ${exportNames} } from './src/pages/Patient/${from}';`, resolveDir: root, loader: 'ts' },
    bundle: true, platform: 'node', format: 'cjs', write: false, packages: 'external', define, logLevel: 'silent',
  }).outputFiles[0].text;
  const loaded = new Module(path.join(root, `test-${from}.cjs`));
  loaded.filename = path.join(root, `test-${from}.cjs`);
  loaded.paths = module.paths;
  loaded._compile(compiled, loaded.filename);
  return loaded.exports;
}

function loadService() {
  const code = buildSync({
    entryPoints: [path.join(root, 'src/services/patientClinical.ts')],
    bundle: false, platform: 'node', format: 'cjs', write: false, define, logLevel: 'silent',
  }).outputFiles[0].text;
  const calls = [];
  const transport = {
    get: async (url, config) => {
      calls.push(['get', url, config]);
      return { data: url === '/health-records/patient-context' ? { patient_id: 'clinical-patient-1' } : {} };
    },
    post: async (url, body) => { calls.push(['post', url, body]); return { data: {} }; },
  };
  const service = new Module(path.join(root, 'test-patient-clinical.cjs'));
  service.filename = path.join(root, 'test-patient-clinical.cjs');
  service.paths = module.paths;
  service.require = name => (name === './httpClient' ? transport : require(name));
  service._compile(code, service.filename);
  return { api: service.exports.patientClinical, calls };
}

test('patient clinical service uses patient self-fetch endpoints only', async () => {
  const { api, calls } = loadService();
  const controller = new AbortController();
  await api.education(controller.signal);
  await api.acknowledgeEducation('a'.repeat(24), '已阅读');
  await api.indicators('patient-1', controller.signal);
  await api.alerts('patient-1', 20, 50, controller.signal);
  assert.equal(await api.selfId(controller.signal), 'clinical-patient-1');
  assert.equal(calls[0][1], '/clinical/education');
  assert.equal(calls[0][2].signal, controller.signal);
  assert.equal(calls[1][1], '/clinical/education/assignments/' + 'a'.repeat(24) + '/read');
  assert.deepEqual(calls[1][2], { feedback: '已阅读' });
  assert.equal(calls[2][1], '/clinical/patients/patient-1/indicators');
  assert.equal(calls[3][1], '/clinical/patients/patient-1/alerts');
  assert.deepEqual(calls[3][2].params, { skip: 20, limit: 50 });
  assert.equal(calls[4][1], '/health-records/patient-context');
  assert.equal(calls[4][2].signal, controller.signal);
  // 患者端服务不提供任何写路径（除本人阅读反馈）
  const endpoints = Object.getOwnPropertyNames(api);
  assert.deepEqual(endpoints.sort(), ['acknowledgeEducation', 'alerts', 'education', 'indicators', 'selfId'].sort());
});

test('education helpers keep backend status vocabulary and feedback limit', () => {
  const view = compilePage('Education.tsx', 'educationStatusLabel, validEducationFeedback');
  assert.equal(view.educationStatusLabel('assigned'), '未读');
  assert.equal(view.educationStatusLabel('read'), '已读');
  assert.equal(view.educationStatusLabel(undefined), '未读');
  // 后端 FEEDBACK_TOO_LONG 上限 1000；空反馈合法（可选项）
  assert.equal(view.validEducationFeedback(''.padEnd(1000, '字')), true);
  assert.equal(view.validEducationFeedback(''.padEnd(1001, '字')), false);
  assert.equal(view.validEducationFeedback('  阅读完成  '), true);
});

test('health status helpers map indicator and alert vocabulary honestly', () => {
  const view = compilePage('HealthStatus.tsx',
    'indicatorStateLabel, alertLevelLabel, alertStatusLabel, boundsText');
  assert.equal(view.indicatorStateLabel('inside'), '达标');
  assert.equal(view.indicatorStateLabel('outside'), '超出范围');
  assert.equal(view.indicatorStateLabel('missing'), '暂无数据');
  // 未知取值如实回显，不臆造标签
  assert.equal(view.indicatorStateLabel('future-state'), 'future-state');
  assert.equal(view.alertLevelLabel('critical'), '危急');
  assert.equal(view.alertLevelLabel('warning'), '警告');
  assert.equal(view.alertStatusLabel('resolved'), '已解决');
  assert.equal(view.alertStatusLabel('ignored'), '已忽略');
  assert.equal(view.boundsText(60, 100, 'mmHg'), '60 ~ 100 mmHg');
  assert.equal(view.boundsText(3.9, null, 'mmol/L'), '≥ 3.9 mmol/L');
  assert.equal(view.boundsText(null, 5, ''), '≤ 5');
  assert.equal(view.boundsText(null, null, ''), '未设上下限');
});

test('follow-up list helpers gate detail navigation to valid record ids', () => {
  const view = compilePage('MyFollowUps.tsx', 'canOpenFollowUpDetail, sortFollowUpsByScheduled');
  assert.equal(view.canOpenFollowUpDetail({ id: '507f1f77bcf86cd799439011' }), true);
  assert.equal(view.canOpenFollowUpDetail({ id: 'not-an-id' }), false);
  assert.equal(view.canOpenFollowUpDetail(null), false);
  const later = { id: 'b'.repeat(24), scheduled_date: '2026-12-01' };
  const earlier = { id: 'a'.repeat(24), scheduled_date: '2026-11-01' };
  const missing = { id: 'c'.repeat(24), scheduled_date: null };
  const sorted = view.sortFollowUpsByScheduled([later, missing, earlier]);
  assert.deepEqual(sorted.map(row => row.id), [earlier.id, later.id, missing.id]);
});
