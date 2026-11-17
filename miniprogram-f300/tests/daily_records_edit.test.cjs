const assert = require('node:assert/strict');
const path = require('node:path');
const test = require('node:test');

const projectRoot = path.resolve(__dirname, '..');
const apiPath = path.join(projectRoot, 'miniprogram/services/api.js');
const pagePath = path.join(projectRoot, 'miniprogram/pages/patient/daily-records/index.js');

function loadPage({ session, respond, wxStub = {} }) {
  let definition;
  const calls = [];
  const api = {
    getSession: () => typeof session === 'function' ? session() : session,
    request: async (url, options = {}) => {
      calls.push({ url, options });
      return respond(url, options, calls.length);
    },
  };
  const previousPage = global.Page;
  global.Page = (page) => { definition = page; };
  const wx = { showModal() {}, stopPullDownRefresh() {}, ...wxStub };
  global.wx = wx;
  require.cache[apiPath] = { id: apiPath, filename: apiPath, loaded: true, exports: api };
  delete require.cache[pagePath];
  require(pagePath);
  delete require.cache[apiPath];
  global.Page = previousPage;
  const page = {
    data: structuredClone(definition.data || {}),
    setData(patch) { Object.assign(this.data, patch); },
  };
  Object.keys(definition).forEach((key) => {
    if (typeof definition[key] === 'function') page[key] = definition[key];
  });
  return { page, calls, wx };
}

test.afterEach(() => { delete global.wx; });

const patientSession = (id = 'patient-1', sessionId = 1) => ({
  user: { id, role: 'patient' }, role: 'patient', identityConfirmed: true, sessionId,
});
const record = (id = 'object:0123456789abcdef01234567') => ({
  id, date: '2026-11-17', pain_level: 4, mood: '一般', sleep: '6小时', exercise_completed: true, note: '活动后疼痛',
});
const validForm = (page) => page.setData({ date: '2026-11-18', painLevel: '3', mood: '好些', sleep: '7小时', exerciseCompleted: false, note: '恢复中' });

test('patient can edit an owned history row through the typed-ID PUT contract', async () => {
  const session = patientSession();
  const original = record();
  const changed = { ...original, date: '2026-11-18', pain_level: 3, mood: '好些', sleep: '7小时', exercise_completed: false, note: '恢复中' };
  const { page, calls } = loadPage({ session, respond: async (url, options) => {
    if (options.method === 'PUT') return changed;
    if (!options.method || options.method === 'GET') return [changed];
    throw new Error(`unexpected request ${options.method} ${url}`);
  } });
  page.data.records = [original];
  page.editRecord({ currentTarget: { dataset: { id: original.id } } });
  assert.equal(page.data.editingRecordId, original.id);
  assert.equal(page.data.painLevel, '4');
  validForm(page);
  await page.saveRecord();
  assert.equal(calls[0].url, `/patients/daily-records/${encodeURIComponent(original.id)}`);
  assert.equal(calls[0].options.method, 'PUT');
  assert.equal(calls[0].options.data.note, '恢复中');
  assert.equal(page.data.records[0].note, '恢复中');
  assert.equal(page.data.editingRecordId, '');
  assert.equal(page.data.success, '日常记录已更新。');
});

test('delete requires explicit confirmation and sends the exact typed record ID', async () => {
  let modal;
  const original = record('string:legacy-daily-id');
  const { page, calls } = loadPage({ session: patientSession(), wxStub: { showModal(options) { modal = options; } }, respond: async (url, options) => {
    if (options.method === 'DELETE') return undefined;
    if (!options.method || options.method === 'GET') return [];
    throw new Error(`unexpected request ${options.method} ${url}`);
  } });
  page.data.records = [original];
  page.confirmDelete({ currentTarget: { dataset: { id: original.id } } });
  assert.equal(calls.length, 0, 'no write before the user confirms');
  assert.match(modal.content, /无法恢复/);
  modal.success({ confirm: false });
  assert.equal(calls.length, 0, 'cancel leaves the record untouched');

  page.confirmDelete({ currentTarget: { dataset: { id: original.id } } });
  modal.success({ confirm: true });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(calls[0].url, `/patients/daily-records/${encodeURIComponent(original.id)}`);
  assert.equal(calls[0].options.method, 'DELETE');
  assert.deepEqual(page.data.records, []);
  assert.equal(page.data.success, '日常记录已删除。');
});

test('record edit/delete responses and a pending confirmation cannot cross an account session', async () => {
  let current = patientSession('patient-a', 1);
  let resolveOldGet;
  let modal;
  const { page, calls } = loadPage({ session: () => current, wxStub: { showModal(options) { modal = options; } }, respond: async (url, options, callNumber) => {
    if (callNumber === 1) return new Promise(resolve => { resolveOldGet = resolve; });
    if (!options.method || options.method === 'GET') return [record('object:aaaaaaaaaaaaaaaaaaaaaaaa')];
    return undefined;
  } });
  const oldPending = page.loadRecords();
  page.data.records = [record('object:bbbbbbbbbbbbbbbbbbbbbbbb')];
  page.confirmDelete({ currentTarget: { dataset: { id: page.data.records[0].id } } });
  current = patientSession('patient-b', 2);
  page.onShow();
  modal.success({ confirm: true });
  resolveOldGet([record('object:cccccccccccccccccccccccc')]);
  await new Promise(resolve => setImmediate(resolve));
  await oldPending;
  assert.equal(calls.filter(call => call.options.method === 'DELETE').length, 0);
  assert.deepEqual(page.data.records.map(item => item.id), ['object:aaaaaaaaaaaaaaaaaaaaaaaa']);
});

test('failed update keeps the editor open and shows the backend error', async () => {
  const original = record();
  const { page, calls } = loadPage({ session: patientSession(), respond: async () => { throw new Error('记录已被移除，请刷新'); } });
  page.data.records = [original];
  page.editRecord({ currentTarget: { dataset: { id: original.id } } });
  validForm(page);
  await page.saveRecord();
  assert.equal(calls[0].options.method, 'PUT');
  assert.equal(page.data.editingRecordId, original.id);
  assert.equal(page.data.error, '记录已被移除，请刷新');
  assert.equal(page.data.saving, false);
});

test('an empty pain value is rejected instead of being submitted as zero', async () => {
  const { page, calls } = loadPage({ session: patientSession(), respond: async () => [] });
  page.setData({ date: '2026-11-18', painLevel: '', mood: '好', sleep: '7小时', exerciseCompleted: false, note: '记录' });
  await page.saveRecord();
  assert.equal(calls.length, 0);
  assert.match(page.data.error, /请填写疼痛程度/);
  page.setData({ painLevel: '   ' });
  await page.saveRecord();
  assert.equal(calls.length, 0);
});

test('a completed old-account write cannot clear records already loaded for the new account', async () => {
  for (const method of ['PUT', 'DELETE']) {
    let current = patientSession('patient-old', 1);
    let resolveWrite;
    const oldRecord = record('object:bbbbbbbbbbbbbbbbbbbbbbbb');
    const newRecord = record('object:aaaaaaaaaaaaaaaaaaaaaaaa');
    const { page, calls } = loadPage({ session: () => current, respond: async (url, options) => {
      if (options.method === method) return new Promise(resolve => { resolveWrite = resolve; });
      if (!options.method || options.method === 'GET') return [newRecord];
      throw new Error(`unexpected request ${options.method} ${url}`);
    } });
    page.data.records = [oldRecord];

    let pending;
    if (method === 'PUT') {
      page.editRecord({ currentTarget: { dataset: { id: oldRecord.id } } });
      validForm(page);
      pending = page.saveRecord();
    } else {
      pending = page.deleteRecord(oldRecord.id, current);
    }

    current = patientSession('patient-new', 2);
    page.onShow();
    await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(page.data.records, [newRecord], `${method}: new session data should load before old write finishes`);

    resolveWrite(method === 'PUT' ? { ...oldRecord, note: 'old account updated' } : undefined);
    await pending;
    assert.deepEqual(page.data.records, [newRecord], `${method}: stale completion must not clear new session records`);
    assert.equal(calls.some(call => call.options.method === method), true);
  }
});
