// T59 医护患者列表分页预适配（前端）契约测试：
// - apiService.doctor.getPatients 缺省请求形态与历史完全一致（不携带参数）；
// - 显式 skip/limit 仅在提供时携带；
// - 患者域错误文案映射覆盖 INVALID_PATIENT_PAGINATION（503）；
// - services/patientList 分页纯逻辑（合并去重/整页判定/加载更多触发阈值）。
const assert = require('node:assert/strict');
const { test } = require('node:test');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const { transformSync } = require('esbuild');

function load(relative, replacements) {
  const file = path.resolve(__dirname, '../src', relative);
  const compiled = new Module(file, module);
  compiled.filename = file;
  compiled.paths = Module._nodeModulePaths(__dirname);
  compiled.require = name => name in replacements ? replacements[name] : require(name);
  compiled._compile(transformSync(readFileSync(file, 'utf8'), { loader: 'ts', format: 'cjs' }).code, file);
  return compiled.exports;
}

function axiosErrorShape(status, code) {
  return { response: { status, data: { error: code } }, message: `Request failed with status code ${status}` };
}

test('doctor getPatients keeps the default one-shot request unchanged', async () => {
  const calls = [];
  const transport = { get: async (...args) => { calls.push(args); return { data: [] }; } };
  const { apiService } = load('services/api.ts', {
    './httpClient': transport,
    '../config/apiPaths': { API_COLLECTION_PATHS: { DEVICES: '/devices/' } },
  });
  await apiService.doctor.getPatients();
  assert.deepEqual(calls, [['/doctors/patients']]);
});

test('doctor getPatients carries explicit skip/limit only when provided', async () => {
  const calls = [];
  const transport = { get: async (...args) => { calls.push(args); return { data: [] }; } };
  const { apiService } = load('services/api.ts', {
    './httpClient': transport,
    '../config/apiPaths': { API_COLLECTION_PATHS: { DEVICES: '/devices/' } },
  });
  await apiService.doctor.getPatients({ skip: 50, limit: 50 });
  await apiService.doctor.getPatients({ skip: 100 });
  await apiService.doctor.getPatients({ limit: 200 });
  await apiService.doctor.getPatients({});
  assert.deepEqual(calls, [
    ['/doctors/patients', { params: { skip: 50, limit: 50 } }],
    ['/doctors/patients', { params: { skip: 100, limit: undefined } }],
    ['/doctors/patients', { params: { skip: undefined, limit: 200 } }],
    ['/doctors/patients'],
  ]);
});

test('INVALID_PATIENT_PAGINATION maps through the patient-domain error copy', () => {
  const { patientDomainErrorCopy, PATIENT_DOMAIN_ERROR_COPY } = load('services/patientErrors.ts', {});
  const copy = PATIENT_DOMAIN_ERROR_COPY.INVALID_PATIENT_PAGINATION;
  assert.ok(copy, 'INVALID_PATIENT_PAGINATION 必须登记统一文案');
  assert.ok(copy.includes('分页'), '文案应说明分页参数问题');
  assert.equal(patientDomainErrorCopy(axiosErrorShape(503, 'INVALID_PATIENT_PAGINATION')), copy);
  assert.equal(patientDomainErrorCopy(axiosErrorShape(503, 'UNKNOWN_PATIENT_CODE')), null);
  assert.equal(patientDomainErrorCopy(axiosErrorShape(400, 'INVALID_PATIENT_PAGINATION')), null);
});

test('patientList merge batches dedupes by id and keeps load order', () => {
  const { mergePatientBatches } = load('services/patientList.ts', {});
  assert.deepEqual(mergePatientBatches([], []), []);
  assert.deepEqual(
    mergePatientBatches([{ id: 'a' }, { id: 'b' }], [{ id: 'b' }, { id: 'c' }]),
    [{ id: 'a' }, { id: 'b' }, { id: 'c' }]);
  // 非法元素（缺失字符串 id）不进入结果
  assert.deepEqual(
    mergePatientBatches([{ id: 'a' }], [null, {}, { id: '' }, { id: 'd' }]),
    [{ id: 'a' }, { id: 'd' }]);
  // 追加批次可安全归并到已有追加结果上
  assert.deepEqual(
    mergePatientBatches([{ id: 'c' }], [{ id: 'c' }, { id: 'd' }]),
    [{ id: 'c' }, { id: 'd' }]);
});

test('patientList paging thresholds follow the backend contract', () => {
  const { patientBatchComplete, patientLoadMoreAvailable,
    PATIENT_LIST_PAGE_SIZE, PATIENT_LIST_ONE_SHOT_CAP } = load('services/patientList.ts', {});
  // 后端分页约束：1≤limit≤200；canonical 缺省一次性返回上限为 100
  assert.equal(PATIENT_LIST_PAGE_SIZE <= 200, true);
  assert.equal(PATIENT_LIST_ONE_SHOT_CAP, 100);
  // 不足一页（含空页）即全部加载
  assert.equal(patientBatchComplete(50), false);
  assert.equal(patientBatchComplete(49), true);
  assert.equal(patientBatchComplete(0), true);
  // 达到一次性上限且未确认加载完才出现「加载更多」
  assert.equal(patientLoadMoreAvailable(100, false), true);
  assert.equal(patientLoadMoreAvailable(99, false), false);
  assert.equal(patientLoadMoreAvailable(150, true), false);
});
