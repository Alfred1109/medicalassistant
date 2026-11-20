const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');
const apiFactory = require('../miniprogram/services/api').createClient;

function harness(handler, { miniToken = 'test-token', storedToken = '' } = {}) {
  let page;
  const calls = [];
  const downloads = [];
  const wx = {
    getStorageSync(key) { return key === 'rehab_access_token' ? storedToken : ''; }, removeStorageSync() {}, stopPullDownRefresh() {},
    request(options) {
      calls.push({ url: options.url, method: options.method || 'GET', data: options.data });
      Promise.resolve(handler(options, calls.length - 1)).then(
        data => options.success({ statusCode: 200, data }),
        error => options.success({ statusCode: error.statusCode || 500, data: { detail: error.message } }),
      );
    },
    downloadFile(options) { downloads.push(options); return { abort() {} }; },
  };
  const api = apiFactory('https://rehab.example/api', () => wx);
  api.setSession({ id: 'doctor-1', role: 'doctor' });
  api.setMiniToken(miniToken);
  const context = {
    wx, Page(definition) { page = definition; }, Date, Promise, Number, String, Array, Math, Intl,
    encodeURIComponent, JSON,
    require(name) {
      if (name === '../../../services/api') return api;
      if (name === '../../../config') return { apiBaseUrl: 'https://rehab.example/api' };
      throw new Error(`Unexpected require: ${name}`);
    },
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../miniprogram/pages/clinical/training/index.js'), 'utf8'), context);
  page.data = { ...page.data, patientId: 'patient-1' };
  page._generation = 0;
  page._identity = 'doctor:doctor-1:1';
  page.setData = values => {
    for (const [key, value] of Object.entries(values)) {
      const parts = key.replace(/\[(\d+)\]/g, '.$1').split('.');
      let target = page.data;
      while (parts.length > 1) target = target[parts.shift()];
      target[parts[0]] = value;
    }
  };
  return { page, api, calls, downloads };
}

test('training page loads clinician-scoped plans, cycles and feedback videos', async () => {
  const cycle = { id: 'cycle-1', title: '第一周期', start_date: '2026-01-01', end_date: '2026-01-31', status: 'open', revision: 0, feedback_count: 1, verified_count: 0, pending_reviews_count: 1 };
  const feedback = { id: 'feedback-1', execution_status: 'completed', intervention_type: 'exercise', performed_at: '2026-01-15T00:00:00Z', attachments: [{ id: 'media-1', name: '训练.mp4', content_type: 'video/mp4' }], supplements: [{ note: '补充正面视角', submitted_at: '2026-01-16T00:00:00Z', attachments: [{ id: 'media-2', name: '补充.mp4', content_type: 'video/mp4' }] }], clinical_review: { status: 'pending', revision: 1 } };
  const { page, calls, downloads } = harness(request => {
    if (request.url.includes('/rehabilitation/plans?')) return [{ id: 'plan-1', name: '膝关节训练', status: 'active' }];
    if (request.url.endsWith('/training-cycles')) return { items: [cycle], total: 1 };
    if (request.url.includes('/patient-feedback?')) return { items: [feedback], total: 1 };
    throw new Error(`Unexpected API call: ${request.url}`);
  });
  await page.loadPlans();
  assert.equal(page.data.selectedPlanId, 'plan-1');
  assert.equal(page.data.cycles[0].canAccept, false);
  assert.equal(page.data.feedback[0].reviewLabel, '待核验');
  assert.equal(downloads.length, 0, 'private videos are loaded only after the clinician requests them');
  const loading = page.loadFeedbackVideos({ currentTarget: { dataset: { index: '0' } } });
  assert.equal(downloads.length, 1, 'video attachments are downloaded sequentially for the selected feedback');
  assert.match(downloads[0].url, /media\/media-1$/);
  assert.equal(downloads[0].header.Authorization, 'Bearer test-token');
  downloads[0].success({ statusCode: 200, tempFilePath: '/tmp/training.mp4' });
  while (downloads.length < 2) await new Promise(resolve => setTimeout(resolve, 0));
  assert.match(downloads[1].url, /media\/media-2$/);
  downloads[1].success({ statusCode: 200, tempFilePath: '/tmp/supplement.mp4' });
  await loading;
  assert.equal(page.data.feedback[0].videos[0].url, '/tmp/training.mp4');
  assert.equal(page.data.feedback[0].videos[1].supplementNote, '补充正面视角');
  assert.equal(page.data.feedback[0].videoReady, true);
  assert.ok(calls.some(call => call.url.includes('patient_id=patient-1')));
});

test('clinician can create a cycle and review feedback using revisioned API contracts', async () => {
  const requests = [];
  const { page, calls } = harness(request => {
    requests.push(request);
    if (request.method === 'POST') return { id: 'saved' };
    if (request.url.endsWith('/training-cycles')) return { items: [], total: 0 };
    if (request.url.includes('/patient-feedback?')) return { items: [], total: 0 };
    throw new Error(`Unexpected API call: ${request.url}`);
  });
  page.data = { ...page.data, plans: [{ id: 'plan-1', status: 'active' }], selectedPlanId: 'plan-1', cycles: [], feedback: [] };
  page.onCycleTitle({ detail: { value: '阶段一' } });
  page.onCycleStart({ detail: { value: '2026-11-01' } });
  page.onCycleEnd({ detail: { value: '2026-11-30' } });
  await page.createCycle();
  const create = requests.find(request => request.method === 'POST');
  assert.deepEqual(JSON.parse(JSON.stringify(create.data)), {
    request_id: create.data.request_id, title: '阶段一', start_date: '2026-11-01', end_date: '2026-11-30',
  });
  assert.match(create.data.request_id, /^[A-Za-z0-9_-]{8,128}$/);
  assert.equal(page.data.message, '训练周期已保存。', 'refresh preserves the mutation result for the clinician');

  page.data = { ...page.data, plans: [{ id: 'plan-1', name: '方案一' }, { id: 'plan-2', name: '方案二' }],
    cycleNotes: { 'cycle-1': '方案一的验收记录' }, editingCycle: { id: 'cycle-2' }, cycleTitle: '旧标题', cycleStart: '2999-01-01', cycleEnd: '2999-01-02' };
  await page.selectPlan({ currentTarget: { dataset: { id: 'plan-2' } } });
  assert.deepEqual(JSON.parse(JSON.stringify(page.data.cycleNotes)), {});
  assert.equal(page.data.editingCycle, null);
  assert.equal(page.data.cycleTitle, '');
  assert.equal(page.data.cycleStart, '');
  assert.equal(page.data.cycleEnd, '');

  page.data = { ...page.data, saving: false, selectedPlanId: 'plan-1', cycles: [{ id: 'future-cycle', title: '待开始', start_date: '2999-01-01', end_date: '2999-01-31', status: 'open', feedback_count: 0, revision: 3, canEdit: true }] };
  page.editCycle({ currentTarget: { dataset: { index: '0' } } });
  page.onCycleTitle({ detail: { value: '待开始周期调整' } });
  await page.createCycle();
  const update = requests.find(request => request.method === 'PUT');
  assert.deepEqual(JSON.parse(JSON.stringify(update.data)), {
    request_id: update.data.request_id, expected_revision: 3, title: '待开始周期调整', start_date: '2999-01-01', end_date: '2999-01-31',
  });

  page.data = { ...page.data, saving: false, selectedPlanId: 'plan-1', feedback: [{ id: 'feedback-2', clinical_review: { revision: 4 }, note: '动作幅度不清楚', videoReady: true, hasVideo: true }] };
  page.data.feedback[0].canReview = true;
  await page.reviewFeedback({ currentTarget: { dataset: { index: '0', status: 'return_for_supplement' } } });
  const review = requests.find(request => request.url.includes('/review'));
  assert.deepEqual(JSON.parse(JSON.stringify(review.data)), { expected_revision: 4, status: 'return_for_supplement', note: '动作幅度不清楚' });
  assert.ok(calls.some(call => call.method === 'POST' && call.url.includes('/patient-feedback/feedback-2/review')));
  assert.equal(page.data.saving, false);
});

test('clinician can verify feedback and accept an ended cycle with no pending reviews', async () => {
  const today = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai' }).format(new Date());
  const ended = new Date(`${today}T00:00:00+08:00`);
  ended.setDate(ended.getDate() - 2);
  const endDate = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai' }).format(ended);
  const requests = [];
  const { page } = harness(request => {
    requests.push(request);
    if (request.method === 'POST') return { cycle: { status: 'accepted' } };
    if (request.url.endsWith('/training-cycles')) return { items: [], total: 0 };
    if (request.url.includes('/patient-feedback?')) return { items: [], total: 0 };
    throw new Error(`Unexpected API call: ${request.url}`);
  });
  page.data = { ...page.data, plans: [{ id: 'plan-1', status: 'active' }], selectedPlanId: 'plan-1',
    feedback: [{ id: 'feedback-3', clinical_review: { revision: 2 }, note: '视频动作符合要求', videoReady: true, canReview: true, hasVideo: true }],
    cycles: [{ id: 'cycle-9', status: 'open', end_date: endDate, pending_reviews_count: 0, revision: 6 }], cycleNotes: { 'cycle-9': '完成本周期复核' } };
  await page.reviewFeedback({ currentTarget: { dataset: { index: '0', status: 'verified' } } });
  const review = requests.find(request => request.url.includes('/review'));
  assert.deepEqual(JSON.parse(JSON.stringify(review.data)), { expected_revision: 2, status: 'verified', note: '视频动作符合要求' });

  page.data = { ...page.data, saving: false, cycles: [{ id: 'cycle-9', status: 'open', end_date: endDate, pending_reviews_count: 0, revision: 6 }], cycleNotes: { 'cycle-9': '完成本周期复核' } };
  await page.acceptCycle({ currentTarget: { dataset: { index: '0' } } });
  const acceptance = requests.find(request => request.url.includes('/acceptance'));
  assert.deepEqual(JSON.parse(JSON.stringify(acceptance.data)), {
    request_id: acceptance.data.request_id, expected_revision: 6, note: '完成本周期复核',
  });
  assert.match(acceptance.data.request_id, /^[A-Za-z0-9_-]{8,128}$/);
});

test('training actions reject missing clinician identity and return reasons are required', async () => {
  const { page, api, calls } = harness(() => []);
  api.clearSession();
  assert.equal(page.identity(), '');
  page.data = { ...page.data, cycleTitle: '阶段一', cycleStart: '2026-01-01', cycleEnd: '2026-01-02', selectedPlanId: 'plan-1' };
  await page.createCycle();
  assert.equal(calls.length, 0);

  api.setSession({ id: 'doctor-1', role: 'doctor' });
  page._identity = page.identity();
  page.data = { ...page.data, plans: [{ id: 'plan-1', status: 'active' }], selectedPlanId: 'plan-1', feedback: [{ id: 'feedback-1', clinical_review: { revision: 0 }, note: '', videoReady: false, hasVideo: false, canReview: true }] };
  await page.reviewFeedback({ currentTarget: { dataset: { index: '0', status: 'return_for_supplement' } } });
  assert.equal(calls.length, 0);
  assert.match(page.data.error, /填写原因/);
  page.onReviewNote({ currentTarget: { dataset: { index: '0' } }, detail: { value: '该历史记录没有视频，请补充训练视频。' } });
  await page.reviewFeedback({ currentTarget: { dataset: { index: '0', status: 'return_for_supplement' } } });
  const legacyReturn = calls.find(call => call.method === 'POST' && call.url.includes('/patient-feedback/feedback-1/review'));
  assert.equal(legacyReturn.data.status, 'return_for_supplement');
  assert.equal(legacyReturn.data.note, '该历史记录没有视频，请补充训练视频。');
});

test('revoked session blocks delayed private-video download from entering page state', async () => {
  const { page, api, downloads } = harness(request => {
    if (request.url.endsWith('/training-cycles')) return { items: [], total: 0 };
    if (request.url.includes('/patient-feedback?')) return { items: [{ id: 'feedback-private', attachments: [{ id: 'private-media', name: 'private.mp4', content_type: 'video/mp4' }] }], total: 1 };
    if (request.url.includes('/rehabilitation/plans?')) return [{ id: 'plan-1', name: '测试方案', status: 'active' }];
    throw new Error(`Unexpected API call: ${request.url}`);
  });
  await page.loadPlans();
  const loading = page.loadFeedbackVideos({ currentTarget: { dataset: { index: '0' } } });
  assert.equal(downloads.length, 1);
  assert.equal(downloads[0].header.Authorization, 'Bearer test-token');
  api.clearSession();
  page.onShow();
  downloads[0].success({ statusCode: 200, tempFilePath: '/tmp/should-not-appear.mp4' });
  await loading;
  assert.equal(page.data.feedback.length, 0);
  assert.match(page.data.error, /身份已变化/);
});

test('video download resolves the legacy access token through the shared API client', async () => {
  const { page, downloads } = harness(request => {
    if (request.url.includes('/rehabilitation/plans?')) return [{ id: 'plan-1', name: '方案一', status: 'active' }];
    if (request.url.endsWith('/training-cycles')) return { items: [], total: 0 };
    if (request.url.includes('/patient-feedback?')) return { items: [{ id: 'f1', intervention_type: 'exercise', execution_status: 'completed',
      attachments: [{ id: 'legacy-media', name: 'legacy.mp4', content_type: 'video/mp4' }] }], total: 1 };
    throw new Error(`Unexpected API call: ${request.url}`);
  }, { miniToken: '', storedToken: 'legacy-token' });
  await page.loadPlans();
  const loading = page.loadFeedbackVideos({ currentTarget: { dataset: { index: '0' } } });
  assert.equal(downloads[0].header.Authorization, 'Bearer legacy-token');
  downloads[0].success({ statusCode: 200, tempFilePath: '/tmp/legacy.mp4' });
  await loading;
  assert.equal(page.data.feedback[0].videoReady, true);
});
