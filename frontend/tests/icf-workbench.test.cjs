// ICF 工作台（T71）纯逻辑与传输层测试：限定值校验、域分组、指标展示、
// 类目校验、患者去重、API 路径契约。页面逻辑抽在 src/utils/icf.ts，
// 传输层抽在 src/services/icfService.ts（esbuild 打包后在 vm 中加载，
// 沿用 tests/quality-workbench.test.cjs 的模式）。
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { buildSync, transformSync } = require('esbuild');
const root = path.resolve(__dirname, '..');

const utilsBundle = buildSync({
  entryPoints: [path.join(root, 'src/utils/icf.ts')],
  bundle: true, platform: 'node', format: 'cjs', write: false,
}).outputFiles[0].text;
const utilsLoaded = { exports: {} };
vm.runInNewContext(utilsBundle, { module: utilsLoaded, exports: utilsLoaded.exports, require, Date, console });
const icf = utilsLoaded.exports;

const serviceSource = transformSync(
  fs.readFileSync(path.join(root, 'src/services/icfService.ts'), 'utf8'),
  { loader: 'ts', format: 'cjs' }).code;

function loadService(transport, apiBaseUrl) {
  const module = { exports: {} };
  vm.runInNewContext(serviceSource, {
    module, exports: module.exports,
    require: (name) => {
      // esbuild __toESM 互操作：默认导入的模块直接返回本体（同 quality 测试模式）。
      if (name.endsWith('httpClient')) return transport;
      return { API_BASE_URL: apiBaseUrl };
    },
    encodeURIComponent,
  });
  return module.exports.icfApi;
}

test('qualifier labels cover numeric 0-4 and pass text through', () => {
  assert.equal(icf.icfQualifierLabel(0), '无问题');
  assert.equal(icf.icfQualifierLabel(4), '完全');
  assert.equal(icf.icfQualifierLabel(2), '中度');
  assert.equal(icf.icfQualifierLabel('尚可'), '尚可');
  assert.equal(icf.icfQualifierLabel(undefined), '');
});

test('validateIcfItems accepts numeric and text qualifiers and rejects bad input', () => {
  const items = icf.validateIcfItems([
    { code: ' B130 ', qualifier: 3 },
    { code: 'd450', qualifier: ' 尚可步行 ', note: '随访' },
  ]);
  assert.deepEqual(items.map(item => item.code), ['b130', 'd450']);
  assert.equal(items[1].qualifier, '尚可步行');
  assert.throws(() => icf.validateIcfItems([]), /至少录入一个/);
  assert.throws(() => icf.validateIcfItems([{ code: 'b130', qualifier: 5 }]), /0-4 的整数/);
  assert.throws(() => icf.validateIcfItems([{ code: 'b130', qualifier: -1 }]), /0-4 的整数/);
  assert.throws(() => icf.validateIcfItems([{ code: 'b130', qualifier: '' }]), /定性限定值/);
  assert.throws(() => icf.validateIcfItems([
    { code: 'b130', qualifier: 1 }, { code: 'B130', qualifier: 2 }]), /重复录入/);
  assert.throws(() => icf.validateIcfItems([{ code: 'b130' }]), /缺失或类型无效/);
});

test('groupIcfItemsByDomain keeps the three ICF domains and defaults unknown to body', () => {
  const grouped = icf.groupIcfItemsByDomain([
    { code: 'b130', name: '精力', domain: 'body', qualifier: 1, qualifier_kind: 'numeric' },
    { code: 'd450', name: '步行', domain: 'activity', qualifier: 2, qualifier_kind: 'numeric' },
    { code: 'd710', name: '互动', domain: 'participation', qualifier: '受限', qualifier_kind: 'text' },
    { code: 'x999', name: '未知', domain: 'context', qualifier: 0, qualifier_kind: 'numeric' },
  ]);
  assert.deepEqual(Object.keys(grouped).sort(), ['activity', 'body', 'participation']);
  assert.equal(grouped.body.length, 2);
  assert.equal(grouped.activity.length, 1);
  assert.equal(grouped.participation.length, 1);
});

test('metric presentation maps states and renders rates and improvements', () => {
  assert.equal(icf.icfMetricStateLabel('alert'), '触发预警');
  assert.equal(icf.icfMetricStateLabel('ok'), '正常');
  assert.equal(icf.icfMetricStateLabel('insufficient_data'), '数据不足');
  assert.equal(icf.icfMetricStateLabel('disabled'), '已停用');
  assert.equal(icf.icfMetricStateLabel('custom_state'), 'custom_state');
  assert.equal(icf.icfMetricValueText({ metric_key: 'attainment_rate', state: 'ok', value: 0.667, threshold: 0.6 }), '67%');
  assert.equal(icf.icfMetricValueText({ metric_key: 'followup_completion_rate', state: 'alert', value: 0.5, threshold: 0.8 }), '50%');
  assert.equal(icf.icfMetricValueText({ metric_key: 'qualifier_improvement', state: 'alert', value: 2, threshold: 1 }), '2 个类目未达标');
  assert.equal(icf.icfMetricValueText({ metric_key: 'qualifier_improvement', state: 'insufficient_data', value: null, threshold: 1 }), '—');
});

test('category form validation enforces code shape, name length and domain enum', () => {
  icf.validateIcfCategory('B900', '自定义类目', 'body');
  assert.throws(() => icf.validateIcfCategory('900', '名称', 'body'), /字母开头/);
  assert.throws(() => icf.validateIcfCategory('b900', '', 'body'), /1-80 个字符/);
  assert.throws(() => icf.validateIcfCategory('b900', '名称'.repeat(50), 'body'), /1-80 个字符/);
  assert.throws(() => icf.validateIcfCategory('b900', '名称', 'context'), /域分类必须/);
});

test('icfError prefers backend conflict/permission copy over fallback', () => {
  const conflict = { response: { status: 409, data: { detail: { code: 'X' } } } };
  assert.match(icf.icfError(conflict, 'fallback'), /重新加载核对/);
  const forbidden = { response: { status: 403 } };
  assert.match(icf.icfError(forbidden, 'fallback'), /无权/);
  const backendMessage = { response: { status: 400, data: { message: '后端说明' } } };
  assert.equal(icf.icfError(backendMessage, 'fallback'), '后端说明');
  // 本地校验错误：调用方把自身 message 作为 fallback 传入（页面 run 的约定）。
  assert.equal(icf.icfError(new Error('本地校验'), '本地校验'), '本地校验');
  assert.equal(icf.icfError({}, 'fallback'), 'fallback');
});

test('icf transport uses the /icf router contract and encodes identifiers', async () => {
  const calls = [];
  const transport = Object.fromEntries(['get', 'post', 'put'].map(method => [method,
    async (...args) => { calls.push({ method, args }); return { data: {} }; }]));
  const api = loadService(transport, '/medical/api');
  await api.categories();
  await api.createAssessment('p 1', { items: [{ code: 'b130', qualifier: 1 }] });
  await api.reviewReport('r 1', { accepted: true, note: '同意', expected_version: 0 });
  await api.updateMetricConfig('attainment_rate', { params: { min_rate: 0.5 } });
  await api.exportReportJson('r1');
  const paths = calls.map(call => `${call.method} ${call.args[0]}`);
  assert.deepEqual(paths, [
    'get /icf/categories',
    'post /icf/patients/p%201/assessments',
    'post /icf/reports/r%201/review',
    'put /icf/metric-configs/attainment_rate',
    'get /icf/reports/r1/export.json',
  ]);
  assert.equal(api.exportReportHtmlUrl('r1'), '/medical/api/icf/reports/r1/export.html');
});
