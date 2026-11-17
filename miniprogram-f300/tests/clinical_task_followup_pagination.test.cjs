const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

function harness(handler) {
  let page;
  let session = { identityConfirmed: true, role: 'doctor', sessionId: 1, user: { id: 'doctor-1' } };
  const calls = [];
  const api = {
    getSession: () => session,
    setSession(value) { session = value; },
    async request(url, options = {}) {
      calls.push({ url, options });
      return handler(url, options, calls.length - 1);
    },
  };
  const context = {
    URL, Promise, Number, String, Array, Math, encodeURIComponent,
    wx: {}, Page(definition) { page = definition; },
    require(name) {
      if (name === '../../../services/api') return api;
      if (name === '../../../config') return { apiBaseUrl: 'https://care.example/api' };
      throw new Error(`Unexpected require: ${name}`);
    },
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../miniprogram/pages/clinical/tasks/index.js'), 'utf8'), context);
  page.data = { ...page.data, createOpen: true, candidates: [
    { patient_id: 'patient-a', references: [] },
    { patient_id: 'patient-b', references: [] },
  ] };
  page.setData = (values) => Object.assign(page.data, values);
  page._identityKey = 'doctor:doctor-1:1';
  page._generation = 0;
  page._candidateGeneration = 0;
  page._followupGeneration = 0;
  page._followupPatientId = '';
  page._followupRetryReset = true;
  return { page, api, calls };
}

const makeRows = (start, count, status = 'scheduled') => Array.from({ length: count }, (_, index) => ({
  id: `followup-${start + index}`, description: `随访 ${start + index}`, status,
}));

test('关联随访分页覆盖第 50 条之后，并可在失败后重试当前页', async () => {
  let secondPageAttempts = 0;
  const { page, calls } = harness(async (url) => {
    const query = new URL(`https://care.example${url}`).searchParams;
    const skip = Number(query.get('skip'));
    if (skip === 0) return { items: [...makeRows(0, 49), ...makeRows(49, 1, 'completed')], total: 51, skip, limit: 50 };
    secondPageAttempts += 1;
    if (secondPageAttempts === 1) throw Object.assign(new Error('随访服务暂不可用'), { statusCode: 503 });
    return { items: makeRows(50, 1), total: 51, skip, limit: 50 };
  });

  await page.onPatientChange({ detail: { value: '0' } });
  assert.equal(page.data.followupSkip, 50);
  assert.equal(page.data.followupHasMore, true);
  assert.equal(page.data.followups.length, 49);
  assert.equal(page.data.followupOptions[0].id, '');

  await page.loadMorePatientFollowups();
  assert.match(page.data.followupError, /随访服务暂不可用/);
  assert.equal(page.data.followupSkip, 50);
  assert.equal(page.data.followupHasMore, true);

  await page.retryPatientFollowups();
  assert.equal(page.data.followupError, '');
  assert.equal(page.data.followupSkip, 51);
  assert.equal(page.data.followupHasMore, false);
  assert.equal(page.data.followups.length, 50);
  assert.equal(page.data.followupOptions.length, 51);
  assert.deepEqual(calls.map(({ url }) => new URL(`https://care.example${url}`).searchParams.get('skip')), ['0', '50', '50']);
});

test('切换患者后丢弃旧患者尚未返回的关联随访', async () => {
  const pending = new Map();
  const { page } = harness((url) => new Promise((resolve) => {
    const patientId = new URL(`https://care.example${url}`).searchParams.get('patient_id');
    pending.set(patientId, resolve);
  }));

  page.onPatientChange({ detail: { value: '0' } });
  page.onPatientChange({ detail: { value: '1' } });
  pending.get('patient-b')({ items: makeRows(100, 1), total: 1, skip: 0, limit: 50 });
  await new Promise((resolve) => setImmediate(resolve));
  pending.get('patient-a')({ items: makeRows(0, 1), total: 1, skip: 0, limit: 50 });
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(page.data.followupOptions[1].id, 'followup-100');
  assert.equal(page.data.followups.length, 1);
});

test('账号切换时清空关联随访并丢弃旧账号请求', async () => {
  let releaseFollowups;
  const { page, api } = harness((url) => {
    if (url.startsWith('/health-records/followup-workbench')) return new Promise((resolve) => { releaseFollowups = resolve; });
    return { items: [], total: 0 };
  });

  page.onPatientChange({ detail: { value: '0' } });
  api.setSession({ identityConfirmed: true, role: 'doctor', sessionId: 2, user: { id: 'doctor-2' } });
  page.syncIdentity();
  releaseFollowups({ items: makeRows(0, 1), total: 1, skip: 0, limit: 50 });
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(page.data.actorId, 'doctor-2');
  assert.equal(page.data.followups.length, 0);
  assert.deepEqual(Array.from(page.data.followupOptions, (item) => item.id), ['']);
  assert.equal(page.data.followupError, '');
  assert.equal(page.data.followupLoading, false);
});
