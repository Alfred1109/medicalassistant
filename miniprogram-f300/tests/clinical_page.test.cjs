const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');
const apiFactory = require('../miniprogram/services/api').createClient;
const { patientSelfSnapshotDigest } = require('../miniprogram/utils/reviewEvidence');

function harness(handler) {
  let page;
  const calls = [];
  const wx = {
    getStorageSync() { return ''; }, removeStorageSync() {}, stopPullDownRefresh() {},
    showModal(options) { options.success({ confirm: true }); },
    navigateTo() {},
    request(options) {
      calls.push({ url: options.url, method: options.method || 'GET', data: options.data });
      Promise.resolve(handler(options, calls.length - 1)).then(
        (data) => options.success({ statusCode: 200, data }),
        (error) => options.success({ statusCode: error.statusCode || 500, data: { detail: error.message } }),
      );
    },
  };
  const api = apiFactory('https://rehab.example/api', () => wx);
  const context = {
    wx, Page(definition) { page = definition; }, Date, Promise, Number, String, Array, Math,
    encodeURIComponent, JSON,
    require(name) {
      if (name === '../../../services/api') return api;
      if (name === '../../../utils/reviewEvidence') return require('../miniprogram/utils/reviewEvidence');
      throw new Error(`Unexpected require: ${name}`);
    },
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../miniprogram/pages/clinical/index/index.js'), 'utf8'), context);
  page.data = { ...page.data };
  page._patientsGeneration = 0;
  page._patientGeneration = 0;
  page._overviewGeneration = 0;
  page._reviewGeneration = 0;
  page.setData = (values) => {
    for (const [key, value] of Object.entries(values)) {
      const parts = key.split('.');
      let target = page.data;
      while (parts.length > 1) target = target[parts.shift()];
      target[parts[0]] = value;
    }
  };
  return { page, api, calls };
}

const patient = (id) => ({ id, name: `患者${id}`, diagnosis: '膝关节康复' });
const workbenchPage = (items = [], total = items.length, skip = 0, limit = 50) => ({ items, total, skip, limit, status_counts: {} });

test('doctor directory uses the real list response and keeps paged patients reachable/searchable', async () => {
  const { page, api, calls } = harness((_request, index) => index === 0
    ? Array.from({ length: 100 }, (_, i) => patient(`p${i}`))
    : [patient('p100')]);
  api.setSession({ id: 'doctor-1', role: 'doctor' });
  page._identityKey = 'doctor:doctor-1:1';
  page.data.sessionRole = 'doctor';

  await page.loadPatients(true);
  assert.equal(page.data.patients.length, 100);
  assert.equal(page.data.patientHasMore, true);
  page.onPatientSearch({ detail: { value: 'p100' } });
  assert.equal(page.data.visiblePatients.length, 0);
  await page.loadMorePatients();
  assert.equal(page.data.patients.length, 101);
  assert.equal(page.data.visiblePatients.length, 1);
  assert.match(calls[0].url, /\/doctors\/patients\?skip=0&limit=100$/);
  assert.match(calls[1].url, /\/doctors\/patients\?skip=100&limit=100$/);
});

test('followup creation follows FollowUpRecordCreate and refreshes the workbench response shape', async () => {
  const { page, api, calls } = harness((request) => {
    if (request.method === 'POST' && request.url.endsWith('/health-records/followups')) return { id: 'f1', status: 'scheduled' };
    if (request.url.includes('/doctors/health-records/')) return { allergies: [], medicalHistory: [], rehabHistory: [], medications: [], vitalSigns: [] };
    if (request.url.includes('/health-records/followup-workbench')) return workbenchPage([], 0, 0, 50);
    throw new Error(`Unexpected API call ${request.method} ${request.url}`);
  });
  api.setSession({ id: 'doctor-1', role: 'doctor' });
  page._identityKey = 'doctor:doctor-1:1';
  page.data = { ...page.data, sessionRole: 'doctor', actorId: 'doctor-1', selectedPatientId: 'patient-7',
    selectedPatientName: '患者 patient-7', scheduledDate: '2026-11-17', scheduledTime: '09:30',
    description: '电话核对康复训练执行情况', typeIndex: 0, createOpen: true };

  await page.createFollowup();
  const post = calls.find((call) => call.method === 'POST');
  assert.ok(post);
  assert.deepEqual(JSON.parse(JSON.stringify(post.data)), {
    patient_id: 'patient-7', follow_up_type: 'phone',
    scheduled_date: new Date('2026-11-17T09:30:00').toISOString(),
    provider_id: 'doctor-1', description: '电话核对康复训练执行情况', questions: [],
  });
  assert.equal(page.data.message, '随访计划已保存。');
  assert.match(calls.find((call) => call.url.includes('/followup-workbench')).url, /patient_id=patient-7&skip=0&limit=50$/);
});

test('manual followup submission sends the optimistic version and real completion payload', async () => {
  const { page, api, calls } = harness((request) => {
    if (request.method === 'POST' && request.url.endsWith('/followups/f1/complete')) return { id: 'f1', status: 'in_review' };
    if (request.url.includes('/doctors/health-records/patient-7')) return { allergies: [], medicalHistory: [], rehabHistory: [], medications: [], vitalSigns: [] };
    if (request.url.includes('/health-records/followup-workbench')) return workbenchPage([], 0, 0, 50);
    throw new Error(`Unexpected API call ${request.method} ${request.url}`);
  });
  api.setSession({ id: 'doctor-1', role: 'doctor' });
  page._identityKey = 'doctor:doctor-1:1';
  page.data = { ...page.data, sessionRole: 'doctor', actorId: 'doctor-1', selectedPatientId: 'patient-7',
    completionTarget: { id: 'f1', mutation_version: 3, questions: [{ question_id: 'pain', required: true }] },
    completionAnswers: [{ question_id: 'pain', answer_value: '2', answer_text: '2' }],
    completionResult: '按计划完成训练', completionNotes: '无明显不适' };

  await page.submitCompletion();
  const post = calls.find((call) => call.method === 'POST');
  assert.match(post.url, /\/health-records\/followups\/f1\/complete$/);
  assert.equal(post.data.expected_version, 3);
  assert.equal(post.data.follow_up_result, '按计划完成训练');
  assert.deepEqual(JSON.parse(JSON.stringify(post.data.answers[0])), {
    question_id: 'pain', answer_value: '2', answer_text: '2', answered_at: post.data.answers[0].answered_at,
  });
  assert.ok(Number.isFinite(Date.parse(post.data.actual_date)));
  assert.equal(page.data.completionTarget, null);
  assert.match(page.data.message, /待医护审阅/);
});

test('external review loads the exact confirmed answer snapshot before approval', async () => {
  const record = { id: 'f1', patient_id: 'p1', provider_id: 'doctor-1', status: 'in_review', mutation_version: 4,
    current_evidence: { source: 'external_form' }, effective_response: { task_id: 't1', response_id: 7 } };
  const task = { id: 't1', patientId: 'p1', followupVisitId: 'f1', status: 'confirmed', remoteStatus: 'submitted',
    confirmation: { response_id: 7, remote_status: 'submitted', answers: [{ question_id: 2, answer_text: '已改善' }] } };
  const { page, api, calls } = harness(request => {
    if (request.url.endsWith('/health-records/followups/f1')) return record;
    if (request.url.endsWith('/integrations/forms/fill-tasks/t1')) return task;
    if (request.url.endsWith('/followups/f1/review')) return {};
    return workbenchPage();
  });
  api.setSession({ id: 'doctor-1', role: 'doctor' });
  page._identityKey = 'doctor:doctor-1:1'; page.data.actorId = 'doctor-1'; page.data.sessionRole = 'doctor';
  page.data.overviewItems = [{ ...record, canReview: true }];
  await page.openReview({ currentTarget: { dataset: { id: 'f1' } } });
  assert.equal(page.data.reviewTarget.canApprove, true);
  assert.equal(page.data.reviewEvidenceRows[0].answer, '已改善');
  await page.submitReview({ currentTarget: { dataset: { decision: 'approved' } } });
  const submitted = calls.find(call => call.url.endsWith('/followups/f1/review'));
  assert.equal(submitted.data.expected_version, 4);
  assert.equal(submitted.data.evidence.response_id, 7);
});

test('mismatched external evidence remains reviewable for return but cannot be approved', async () => {
  const record = { id: 'f1', patient_id: 'p1', provider_id: 'doctor-1', status: 'in_review', mutation_version: 4,
    current_evidence: { source: 'external_form' }, effective_response: { task_id: 't1', response_id: 7 } };
  const { page, api } = harness(request => request.url.includes('fill-tasks')
    ? { id: 't1', patientId: 'other', followupVisitId: 'f1', status: 'confirmed', confirmation: { response_id: 7, remote_status: 'submitted', answers: [{ question_id: 2, answer_text: 'x' }] } }
    : record);
  api.setSession({ id: 'doctor-1', role: 'doctor' });
  page._identityKey = 'doctor:doctor-1:1'; page.data.actorId = 'doctor-1'; page.data.sessionRole = 'doctor';
  page.data.overviewItems = [{ ...record, canReview: true }];
  await page.openReview({ currentTarget: { dataset: { id: 'f1' } } });
  assert.equal(page.data.reviewTarget.canApprove, false);
  assert.match(page.data.reviewEvidenceError, /无法核实/);
});

test('patient self-filled evidence is separately loaded and labelled for review', async () => {
  const record = { id: 'f1', patient_id: 'p1', provider_id: 'doctor-1', status: 'in_review', mutation_version: 4,
    current_evidence: { source: 'external_form' }, effective_response: { task_id: 't1', response_id: 7 } };
  const evidence = { fill_mode: 'patient_self', response_id: 7, remote_status: 'submitted', session_uuid: 's1',
    is_voided: false, user_id: null, verified_at: '2026-11-17T00:00:00Z',
    questionnaire_version_ref: { form_id: 10, family_id: 1, version: 1, definition_sha256: 'b'.repeat(64) },
    answers: [{ question_id: 9, answer_text: '患者回答' }] };
  evidence.snapshot_sha256 = patientSelfSnapshotDigest(evidence);
  const { page, api } = harness(request => {
    if (request.url.endsWith('/health-records/followups/f1')) return record;
    if (request.url.includes('/fill-tasks/')) throw Object.assign(new Error('not found'), { statusCode: 404 });
    return { id: 't1', patientId: 'p1', followupVisitId: 'f1', status: 'confirmed',
      remoteRefs: { questionnaire_id: 10 }, session: { status: 'submitted', sessionId: 's1' },
      verifiedEvidence: evidence };
  });
  api.setSession({ id: 'doctor-1', role: 'doctor' });
  page._identityKey = 'doctor:doctor-1:1'; page.data.actorId = 'doctor-1'; page.data.sessionRole = 'doctor';
  page.data.overviewItems = [{ ...record, canReview: true }];
  await page.openReview({ currentTarget: { dataset: { id: 'f1' } } });
  assert.equal(page.data.reviewTarget.canApprove, true);
  assert.equal(page.data.reviewTarget.evidenceLabel, '患者本人填写的问卷');
  assert.equal(page.data.reviewEvidenceRows[0].answer, '患者回答');
});

test('patient self-filled answer tampering invalidates its review digest', () => {
  const crypto = require('node:crypto');
  const evidence = { fill_mode: 'patient_self', session_uuid: 's1', response_id: 1, remote_status: 'submitted',
    submitted_at: '2026-11-17T00:00:00Z', updated_at: '2026-11-17T00:00:00Z',
    questionnaire_version_ref: { form_id: 1, family_id: 2, version: 3, definition_sha256: 'f'.repeat(64) },
    visit_code: null, answers: [{ question_id: 1, answer_text: '康复 🙂' }] };
  const canonical = value => Array.isArray(value) ? `[${value.map(canonical).join(',')}]`
    : value && typeof value === 'object' ? `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`
      : JSON.stringify(value);
  assert.equal(patientSelfSnapshotDigest(evidence), crypto.createHash('sha256').update(canonical(evidence)).digest('hex'));
  assert.equal(patientSelfSnapshotDigest(evidence), 'd66a0a4cbb91c1a047c2da37e99217671e0ac172f3babf98d9c82f241b368328');
  const digest = patientSelfSnapshotDigest(evidence);
  evidence.answers[0].answer_text = 'changed';
  assert.notEqual(patientSelfSnapshotDigest(evidence), digest);
});

test('a patient detail response from a prior login cannot repopulate the new account page', async () => {
  let releaseOldHealth;
  let releaseOldFollowups;
  const { page, api } = harness((request) => {
    if (request.url.includes('/doctors/health-records/old-patient')) return new Promise((resolve) => { releaseOldHealth = resolve; });
    if (request.url.includes('patient_id=old-patient')) return new Promise((resolve) => { releaseOldFollowups = resolve; });
    if (request.url.includes('/doctors/patients')) return [patient('new-patient')];
    return workbenchPage([], 0, 0, 50);
  });
  api.setSession({ id: 'doctor-old', role: 'doctor' });
  page._identityKey = 'doctor:doctor-old:1';
  page.data = { ...page.data, sessionRole: 'doctor', actorId: 'doctor-old', selectedPatientId: 'old-patient',
    selectedPatientName: '旧患者', detailLoading: false };
  const oldRead = page.loadPatientDetail(true);
  while (!releaseOldHealth || !releaseOldFollowups) await new Promise((resolve) => setImmediate(resolve));

  api.setSession({ id: 'doctor-new', role: 'doctor' });
  releaseOldHealth({ id: 'old-patient', allergies: ['旧账号敏感资料'] });
  releaseOldFollowups(workbenchPage([{ id: 'old-followup', patient_id: 'old-patient', status: 'scheduled' }], 1));
  await oldRead;
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(page.data.selectedPatientId, '');
  assert.equal(page.data.healthRecord, null);
  assert.equal(page.data.followups.length, 0);
  assert.deepEqual(page.data.patients.map((item) => item.id), ['new-patient']);
  assert.equal(page.data.actorId, 'doctor-new');
});
