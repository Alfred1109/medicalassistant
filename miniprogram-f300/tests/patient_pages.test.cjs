const assert = require('node:assert/strict');
const path = require('node:path');
const test = require('node:test');

const projectRoot = path.resolve(__dirname, '..');
const apiPath = path.join(projectRoot, 'miniprogram/services/api.js');

function loadPage(relativePath, { session, respond, upload, wxStub = {}, pages = [] }) {
  let definition;
  const calls = [];
  const api = {
    getSession: () => typeof session === 'function' ? session() : session,
    request: async (url, options = {}) => {
      calls.push({ url, options });
      return respond ? respond(url, options, calls.length) : undefined;
    },
    uploadFile: async (url, filePath) => upload ? upload(url, filePath) : ({ id: 'a'.repeat(32), content_type: 'video/mp4', name: 'training.mp4' }),
  };
  const previousPage = global.Page;
  const previousWx = global.wx;
  const previousGetPages = global.getCurrentPages;
  global.Page = (page) => { definition = page; };
  global.wx = {
    showToast() {},
    showModal() {},
    stopPullDownRefresh() {},
    navigateTo() {},
    navigateBack() {},
    ...wxStub,
  };
  global.getCurrentPages = () => pages;
  require.cache[apiPath] = { id: apiPath, filename: apiPath, loaded: true, exports: api };
  const pagePath = path.join(projectRoot, 'miniprogram', relativePath);
  delete require.cache[pagePath];
  require(pagePath);
  delete require.cache[apiPath];
  global.Page = previousPage;
  global.wx = previousWx;
  global.getCurrentPages = previousGetPages;
  const instance = {
    data: structuredClone(definition.data || {}),
    setData(patch) { Object.assign(this.data, patch); },
  };
  Object.keys(definition).forEach((key) => {
    if (typeof definition[key] === 'function') instance[key] = definition[key];
  });
  return { page: instance, calls };
}

const patientSession = (id = 'patient-1', sessionId = 1) => ({
  user: { id, role: 'patient' }, role: 'patient', identityConfirmed: true, sessionId,
});

test('patient questionnaire list only requests own assigned tasks and discards previous-session results', async () => {
  let current = patientSession('patient-1', 1), finish;
  const result = new Promise(resolve => { finish = resolve; });
  const { page, calls } = loadPage('pages/patient/questionnaires/index.js', {
    session: () => current, respond: () => result,
  });
  page.onLoad(); page.onShow();
  assert.equal(calls[0].url, '/integrations/forms/patient-self/tasks?skip=0&limit=50');
  current = patientSession('patient-1', 2);
  finish({ items: [{ id: 'old-task', status: 'assigned' }], total: 1 });
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(page.data.items, []);
});

test('feedback retry preserves the original submission identity and time after a timeout', async () => {
  let posts = 0;
  const session = patientSession();
  const { page, calls } = loadPage('pages/patient/plan-detail/index.js', {
    session,
    respond: async (url, options) => {
      if (options.method === 'POST' && ++posts === 1) throw new Error('网络超时');
      return options.method === 'POST' ? { created: false } : { items: [], total: 0 };
    },
  });
  page.data.planId = 'plan';
  page.data.plan = { version_id: 'v1', items: [{ item_id: 'i1' }] };
  page.data.feelings = '完成训练';
  const previousWx = global.wx;
  global.wx = { showToast() {} };
  try { await page.submitFeedback(); await page.submitFeedback(); }
  finally { global.wx = previousWx; }
  const bodies = calls.filter(call => call.options.method === 'POST').map(call => call.options.data);
  assert.equal(bodies.length, 2);
  assert.deepEqual(bodies[0], bodies[1]);
  assert.equal(page.data.feelings, '');
});

test('feedback history supports more than one page', async () => {
  const { page, calls } = loadPage('pages/patient/plan-detail/index.js', {
    session: patientSession(),
    respond: async url => url.includes('skip=0')
      ? { items: Array.from({ length: 100 }, (_, id) => ({ id })), total: 101 }
      : { items: [{ id: 100 }], total: 101 },
  });
  page.data.planId = 'plan'; page.data.plan = { version_id: 'v1', items: [] };
  await page.loadFeedback(); await page.loadMoreFeedback();
  assert.match(calls[1].url, /skip=100/);
  assert.equal(page.data.feedback.length, 101);
  assert.equal(page.data.feedbackHasMore, false);
});

test('exercise feedback uploads a selected video before submission and reuses it on retry', async () => {
  const session = patientSession();
  let uploads = 0, posts = 0;
  const { page, calls } = loadPage('pages/patient/plan-detail/index.js', {
    session,
    upload: async (url, filePath) => { uploads += 1; assert.match(url, /patient-feedback\/media$/); assert.equal(filePath, '/tmp/training.mp4'); return { id: 'b'.repeat(32), content_type: 'video/mp4', name: 'training.mp4' }; },
    respond: async (url, options) => {
      if (options.method === 'POST') { posts += 1; if (posts === 1) throw new Error('network timeout'); return { created: true }; }
      return { items: [], total: 0 };
    },
  });
  page.data.planId = '0123456789abcdef01234567';
  page.data.plan = { version_id: 'v1', items: [{ item_id: 'i1', intervention_type: 'exercise' }] };
  page.data.selectedVideoPath = '/tmp/training.mp4'; page.data.selectedVideoName = 'training.mp4';
  page.data.feelings = '完成训练';
  const previousWx = global.wx; global.wx = { showToast() {} };
  try { await page.submitFeedback(); await page.submitFeedback(); } finally { global.wx = previousWx; }
  assert.equal(uploads, 1);
  const body = calls.filter(call => call.options.method === 'POST').map(call => call.options.data);
  assert.equal(body.length, 2);
  assert.deepEqual(body[0], body[1]);
  assert.deepEqual(body[0].media_ids, ['b'.repeat(32)]);
});

test('exercise completed feedback cannot be submitted without a video', async () => {
  let posts = 0;
  const { page } = loadPage('pages/patient/plan-detail/index.js', {
    session: patientSession(), respond: async () => { posts += 1; return {}; },
  });
  page.data.planId = '0123456789abcdef01234567';
  page.data.plan = { version_id: 'v1', items: [{ item_id: 'i1', intervention_type: 'exercise' }] };
  page.data.feelings = '完成训练';
  const previousWx = global.wx; global.wx = { showToast() {} };
  try { await page.submitFeedback(); } finally { global.wx = previousWx; }
  assert.equal(posts, 0);
});

test('returned training feedback accepts a video supplement and sends the review request', async () => {
  const calls = [];
  const session = patientSession();
  const { page } = loadPage('pages/patient/plan-detail/index.js', {
    session,
    upload: async () => ({ id: 'c'.repeat(32), content_type: 'video/mp4', name: 'extra.mp4' }),
    respond: async (url, options) => { calls.push({ url, options }); return { items: [], total: 0 }; },
  });
  page.data.planId = '0123456789abcdef01234567';
  page.data.plan = { version_id: 'v1', items: [] };
  page.data.feedback = [{ id: '1123456789abcdef01234567', clinical_review: { status: 'return_for_supplement', note: '请补拍完整动作' }, supplementNote: '已按要求补拍', supplementVideoPath: '/tmp/extra.mp4' }];
  await page.submitSupplement({ currentTarget: { dataset: { index: '0' } } });
  const submission = calls.find(call => call.options.method === 'POST');
  assert.match(submission.url, /patient-feedback\/1123456789abcdef01234567\/supplements$/);
  assert.deepEqual(submission.options.data.media_ids, ['c'.repeat(32)]);
  assert.equal(submission.options.data.note, '已按要求补拍');
});

test('patient plan reads cycle status and discards cycles from a previous login session', async () => {
  let current = patientSession('patient-1', 1), finish;
  const pending = new Promise(resolve => { finish = resolve; });
  const { page, calls } = loadPage('pages/patient/plan-detail/index.js', {
    session: () => current, respond: () => pending,
  });
  page.data.planId = '0123456789abcdef01234567';
  const loading = page.loadTrainingCycles(current);
  assert.equal(calls[0].url, '/rehabilitation/plans/0123456789abcdef01234567/training-cycles');
  current = patientSession('patient-1', 2);
  finish({ items: [{ id: 'cycle-1', status: 'accepted', acceptance: { status: 'accepted', note: '周期完成', accepted_at: '2026-01-01T00:00:00Z' }, feedback_count: 2, verified_count: 2, pending_reviews_count: 0 }], total: 1 });
  await loading;
  assert.deepEqual(page.data.trainingCycles, []);
});

test('video verification state is shown only for completed exercise feedback', async () => {
  const { page } = loadPage('pages/patient/plan-detail/index.js', {
    session: patientSession(),
    respond: async () => ({ items: [
      { id: 'exercise-feedback', version_id: 'v1', prescription_item_id: 'exercise-item', execution_status: 'completed', clinical_review: { status: 'pending', note: '' } },
      { id: 'diet-feedback', version_id: 'v1', prescription_item_id: 'diet-item', execution_status: 'completed', clinical_review: { status: 'pending', note: '' } },
      { id: 'not-done-exercise', version_id: 'v1', prescription_item_id: 'exercise-item', execution_status: 'not_done', clinical_review: { status: 'pending', note: '' } },
      { id: 'old-exercise-feedback', version_id: 'old-version', intervention_type: 'exercise', prescription_item_id: 'old-item', execution_status: 'partial', clinical_review: { status: 'return_for_supplement', note: '请补充' } },
      { id: 'old-unknown-feedback', version_id: 'old-version', prescription_item_id: 'exercise-item', execution_status: 'completed', clinical_review: { status: 'pending', note: '' } },
    ], total: 3 }),
  });
  page.data.planId = '0123456789abcdef01234567';
  page.data.plan = { version_id: 'v1', items: [
    { item_id: 'exercise-item', intervention_type: 'exercise' },
    { item_id: 'diet-item', intervention_type: 'diet' },
  ] };
  await page.loadFeedback();
  assert.equal(page.data.feedback[0].needsTrainingReview, true);
  assert.equal(page.data.feedback[0].reviewStatusLabel, '待医护核验');
  assert.equal(page.data.feedback[1].needsTrainingReview, false);
  assert.equal(page.data.feedback[1].reviewStatusLabel, '');
  assert.equal(page.data.feedback[2].needsTrainingReview, false);
  assert.equal(page.data.feedback[3].needsTrainingReview, true, 'historical feedback uses its API intervention type');
  assert.equal(page.data.feedback[3].reviewStatusLabel, '请补充材料');
  assert.equal(page.data.feedback[4].needsTrainingReview, false, 'never infer an old version type from current plan items');
});

test('patient pages load canonical self-scoped health records and follow-ups with more-page offsets', async () => {
  const recordRows = Array.from({ length: 100 }, (_, index) => ({ id: `record-${index}` }));
  let recordPage = 0;
  const records = loadPage('pages/patient/records/index.js', {
    session: patientSession(),
    respond: async (url) => {
      if (url === '/health-records/patient-context') return { patient_id: 'clinical-patient-1' };
      if (url.includes('skip=0')) { recordPage += 1; return recordRows; }
      return [{ id: 'record-100' }];
    },
  });
  await records.page.loadRecords(true);
  assert.match(records.calls[1].url, /patient_id=clinical-patient-1&skip=0&limit=100/);
  assert.equal(records.page.data.hasMore, true);
  await records.page.loadMore();
  assert.match(records.calls[3].url, /skip=100&limit=100/);
  assert.equal(records.page.data.records.length, 101);

  const followupRows = Array.from({ length: 100 }, (_, index) => ({ id: `followup-${index}`, status: 'scheduled' }));
  const followups = loadPage('pages/patient/followups/index.js', {
    session: patientSession(),
    respond: async (url) => {
      if (url === '/health-records/patient-context') return { patient_id: 'clinical-patient-1' };
      return url.includes('skip=0') ? followupRows : [{ id: 'followup-100', status: 'scheduled' }];
    },
  });
  await followups.page.loadFollowups(true);
  await followups.page.loadMore();
  assert.match(followups.calls[3].url, /skip=100&limit=100/);
  assert.equal(followups.page.data.followups.length, 101);
});

test('published-plan list follows total pagination and clears data on same-user session replacement', async () => {
  const firstPage = Array.from({ length: 100 }, (_, index) => ({ id: `plan-${index}` }));
  const plans = loadPage('pages/patient/plans/index.js', {
    session: patientSession('same-patient', 1),
    respond: async (url) => url.includes('skip=0')
      ? { items: firstPage, total: 101 }
      : { items: [{ id: 'plan-100' }], total: 101 },
  });
  await plans.page.loadPlans(true);
  assert.equal(plans.page.data.hasMore, true);
  await plans.page.loadMore();
  assert.match(plans.calls[1].url, /skip=100&limit=100/);
  assert.equal(plans.page.data.plans.length, 101);

  const newSession = patientSession('same-patient', 2);
  const refresh = loadPage('pages/patient/plans/index.js', {
    session: newSession,
    respond: async () => ({ items: [], total: 0 }),
  });
  refresh.page.data.plans = [{ id: 'old-session-secret' }];
  refresh.page._sessionKey = 'same-patient|1';
  refresh.page.onShow();
  assert.deepEqual(refresh.page.data.plans, []);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(refresh.page.data.plans.length, 0);
});

test('late patient response from previous same-account session is discarded', async () => {
  let currentSession = patientSession('same-patient', 11);
  let resolveRequest;
  const plans = loadPage('pages/patient/plans/index.js', {
    session: () => currentSession,
    respond: () => new Promise((resolve) => { resolveRequest = resolve; }),
  });
  const pending = plans.page.loadPlans(true);
  currentSession = patientSession('same-patient', 12);
  resolveRequest({ items: [{ id: 'old-session-plan' }], total: 1 });
  await pending;
  assert.deepEqual(plans.page.data.plans, []);
  assert.match(plans.page.data.error, /登录状态已变化/);
});

test('consent list resolves patient context and confirmation gates signature before re-reading', async () => {
  const list = loadPage('pages/patient/consents/index.js', {
    session: patientSession(),
    respond: async (url) => url === '/health-records/patient-context'
      ? { patient_id: 'clinical-patient-1' }
      : { documents: [{ id: 'consent-1', title: '治疗说明', body: '全文', status: 'pending' }] },
  });
  await list.page.loadDocuments();
  assert.equal(list.calls[1].url, '/consent/documents?patient_id=clinical-patient-1');
  assert.equal(list.page.data.documents[0].status_label, '待阅读与回应');

  let modal;
  const listPage = { loadDocuments: async () => { listPage.reloaded = true; } };
  let submitPromise;
  const detail = loadPage('pages/patient/consent-detail/index.js', {
    session: patientSession(),
    respond: async (url, options) => {
      if (options.method === 'POST') return { status: 'signed' };
      return { id: 'consent-1', title: '治疗说明', body: '请完整阅读', status: 'signed', signed_name: '张某' };
    },
    wxStub: { showModal: (options) => { modal = options; } },
    pages: [{}, listPage, {}],
  });
  detail.page.data.documentId = 'consent-1';
  detail.page.data.document = { id: 'consent-1', title: '治疗说明', body: '请完整阅读', status: 'pending' };
  detail.page.data.signedName = '张某';
  const originalSubmit = detail.page.submitDecision.bind(detail.page);
  detail.page.submitDecision = (...args) => { submitPromise = originalSubmit(...args); return submitPromise; };
  global.wx = { showModal: (options) => { modal = options; }, showToast() {} };
  global.getCurrentPages = () => [{}, listPage, {}];
  detail.page.confirmAccept();
  assert.equal(detail.calls.length, 0, 'must not write before modal confirmation');
  assert.match(modal.content, /已阅读/);
  await modal.success({ confirm: true });
  await submitPromise;
  assert.equal(detail.calls[0].url, '/consent/documents/consent-1/signature');
  assert.equal(detail.calls[0].options.data.accepted, true);
  assert.equal(detail.calls[1].url, '/consent/documents/consent-1');
  assert.equal(detail.page.data.document.status, 'signed');
  assert.equal(listPage.reloaded, true);
  delete global.wx;
  delete global.getCurrentPages;
});
