const assert = require('node:assert/strict');
const { test } = require('node:test');
const { createHash } = require('node:crypto');
const Module = require('node:module');
const path = require('node:path');
const { buildSync } = require('esbuild');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const filename = path.resolve(__dirname, '.followup-review.compiled.cjs');
const compiled = buildSync({
  stdin: { contents: `export * from './utils/followupReview'; export {FollowUpReviewEvidence} from './components/HealthManager/FollowUpReviewDialog'; export {default as FollowUpList} from './components/HealthManager/FollowUpList'; export {default as FollowUpVisitLinks} from './components/HealthManager/FollowUpVisitLinks';`, resolveDir: path.resolve(__dirname, '../src'), loader: 'ts' },
  bundle: true, platform: 'node', format: 'cjs', write: false, packages: 'external',
  define: { 'import.meta.env.VITE_API_URL': 'undefined', 'import.meta.env.VITE_API_PREFIX': 'undefined' }, logLevel: 'silent',
}).outputFiles[0].text;
const loaded = new Module(filename, module); loaded.filename = filename; loaded.paths = Module._nodeModulePaths(__dirname);
const originalRequire = loaded.require.bind(loaded);
loaded.require = name => { const result = originalRequire(name); return name.startsWith('@mui/icons-material/') ? result.default : result; };
loaded._compile(compiled, filename);
const domain = loaded.exports;
const record = { id: 'visit-1', patient_id: 'patient-1', provider_id: 'doctor-1', created_by: 'doctor-2', status: 'in_review', mutation_version: 4, description: '真实随访', follow_up_type: 'phone', scheduled_date: '2026-11-09T00:00:00Z', created_at: '', updated_at: '' };
const stableJson = value => Array.isArray(value) ? `[${value.map(stableJson).join(',')}]` :
  value && typeof value === 'object' ? `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${stableJson(value[key])}`).join(',')}}` : JSON.stringify(value);
const selfSnapshotHash = evidence => createHash('sha256').update(stableJson({
  fill_mode: evidence.fill_mode, session_uuid: evidence.session_uuid, response_id: evidence.response_id,
  remote_status: evidence.remote_status, submitted_at: evidence.submitted_at, updated_at: evidence.updated_at,
  questionnaire_version_ref: evidence.questionnaire_version_ref, visit_code: evidence.visit_code ?? null,
  answers: evidence.answers,
})).digest('hex');
test('review eligibility requires current medical role, review state and responsible practitioner', () => {
  assert.equal(domain.canReviewFollowUp(record, { id: 'doctor-1', role: 'doctor' }), true);
  assert.equal(domain.canReviewFollowUp(record, { id: 'doctor-2', role: 'health_manager' }), true);
  for (const actor of [null, { id: 'doctor-3', role: 'doctor' }, { id: 'doctor-1', role: 'patient' }]) assert.equal(domain.canReviewFollowUp(record, actor), false);
  assert.equal(domain.canReviewFollowUp({ ...record, status: 'completed' }, { id: 'doctor-1', role: 'doctor' }), false);
});
test('external snapshot must match exact patient, task, response and confirmed state', () => {
  const visit = { ...record, current_evidence: { source: 'external_form' }, effective_response: { task_id: 'task-1', response_id: 42 } };
  const task = { id: 'task-1', patientId: 'patient-1', status: 'confirmed', confirmation: { response_id: 42, remote_status: 'submitted', answers: [{ question_id: 1, answer_text: '真实回答' }] } };
  assert.equal(domain.verifiedReviewTask(visit, task), true);
  for (const invalid of [{ ...task, patientId: 'patient-2' }, { ...task, id: 'task-2' }, { ...task, status: 'submitted' }, { ...task, confirmation: { ...task.confirmation, response_id: 43 } }, { ...task, remoteQueryError: '无法核实' }, { ...task, remoteStatus: 'revoked' }]) assert.equal(domain.verifiedReviewTask(visit, invalid), false);
});
test('patient-self review fallback is 404-only and validates the linked session, version and answers', async () => {
  const visit = { ...record, current_evidence: { source: 'external_form' },
    effective_response: { task_id: 'task-1', response_id: 42 } };
  const raw = {
    id: 'task-1', status: 'confirmed', patientId: 'patient-1', followupVisitId: 'visit-1',
    remoteRefs: { project_id: 1, center_id: 2, subject_id: 3, questionnaire_id: 4 },
    session: { sessionId: 'session-1', status: 'submitted', expiresAt: null },
    verifiedEvidence: {
      fill_mode: 'patient_self', session_uuid: 'session-1', response_id: 42,
      remote_status: 'submitted', is_voided: false, user_id: null,
      submitted_at: '2026-11-17T10:00:00Z', updated_at: '2026-11-17T10:02:00Z',
      questionnaire_version_ref: { form_id: 4, family_id: 4, version: 2, definition_sha256: 'a'.repeat(64) },
      visit_code: null, answers: [{ question_id: 1, answer_text: '患者本人回答' }],
      verified_at: '2026-11-17T10:03:00Z', snapshot_sha256: '',
    },
  };
  raw.verifiedEvidence.snapshot_sha256 = selfSnapshotHash(raw.verifiedEvidence);
  const notFound = Object.assign(new Error('普通任务未找到'), { response: { status: 404 } });
  let selfReads = 0;
  const task = await domain.loadFollowUpReviewTask(visit, 'task-1', {
    getFillTask: async () => { throw notFound; },
    getPatientSelfTask: async id => { selfReads += 1; assert.equal(id, 'task-1'); return raw; },
  });
  assert.equal(selfReads, 1);
  assert.equal(task.evidenceSource, 'patient_self');
  assert.equal(domain.verifiedReviewTask(visit, task), true);
  const html = renderToStaticMarkup(React.createElement(domain.FollowUpReviewEvidence, { record: visit, task }));
  for (const text of ['来源：患者本人填写', '已确认的回答快照', '患者本人回答']) assert.ok(html.includes(text), text);

  const forbidden = Object.assign(new Error('禁止'), { response: { status: 403 } });
  selfReads = 0;
  await assert.rejects(() => domain.loadFollowUpReviewTask(visit, 'task-1', {
    getFillTask: async () => { throw forbidden; },
    getPatientSelfTask: async () => { selfReads += 1; return raw; },
  }));
  assert.equal(selfReads, 0);

  selfReads = 0;
  await assert.rejects(() => domain.loadFollowUpReviewTask(visit, 'task-1', {
    getFillTask: async () => ({ id: 'other-task', patientId: 'patient-1', status: 'confirmed',
      confirmation: { response_id: 42, remote_status: 'submitted', answers: [{ question_id: 1, answer_text: '回答' }] } }),
    getPatientSelfTask: async () => { selfReads += 1; return raw; },
  }));
  assert.equal(selfReads, 0);

  for (const tamper of [
    { patientId: 'patient-2' }, { followupVisitId: 'visit-2' },
    { session: { ...raw.session, sessionId: 'session-2' } },
    { verifiedEvidence: { ...raw.verifiedEvidence, response_id: 43 } },
    { verifiedEvidence: { ...raw.verifiedEvidence, fill_mode: 'clinician' } },
    { verifiedEvidence: { ...raw.verifiedEvidence, questionnaire_version_ref: { ...raw.verifiedEvidence.questionnaire_version_ref, form_id: 99 } } },
    { verifiedEvidence: { ...raw.verifiedEvidence, answers: [] } },
    { verifiedEvidence: { ...raw.verifiedEvidence, answers: [{ question_id: 1, answer_text: '被篡改' }] } },
  ]) {
    const invalid = { ...raw, ...tamper };
    await assert.rejects(() => domain.loadFollowUpReviewTask(visit, 'task-1', {
      getFillTask: async () => { throw notFound; },
      getPatientSelfTask: async () => invalid,
    }));
  }
});
test('manual review renders saved answers and history without executing embedded content', () => {
  const html = renderToStaticMarkup(React.createElement(domain.FollowUpReviewEvidence, { record: { ...record, current_evidence: { source: 'manual_entry', legacy: true }, completion_data: { source: 'manual_entry' }, follow_up_result: '<script>bad()</script>', notes: '真实备注', questions: [{ question_id: 'q1', question_text: '实际问题' }], answers: [{ question_id: 'q1', answer_value: false }], review: { history: [{ decision: 'returned', comment: '补充资料' }] } }, task: null }));
  for (const text of ['手工录入', '真实备注', '实际问题', 'false', '补充资料', '&lt;script&gt;']) assert.ok(html.includes(text), text);
  assert.equal(html.includes('<script>'), false);
});
test('reference alone never pretends to render actual answers; entry appears only for review state', () => {
  const html = renderToStaticMarkup(React.createElement(domain.FollowUpReviewEvidence, { record: { ...record, current_evidence: { source: 'external_form' }, effective_response: { task_id: 'task-1', response_id: 42 } }, task: null }));
  assert.ok(html.includes('答卷引用用于追溯'));
  assert.equal(html.includes('已确认的回答快照'), false);
  const list = status => renderToStaticMarkup(React.createElement(domain.FollowUpList, { records: [{ ...record, status }], onReview() {} }));
  assert.ok(list('in_review').includes('审阅随访'));
  assert.equal(list('completed').includes('审阅随访'), false);
});

test('manual review carries viewed version and omits stale external references', () => {
  const payload = domain.buildFollowUpReviewRequest({ ...record, current_evidence: { source: 'manual_entry', legacy: true }, completion_data: { source: 'manual_entry' }, effective_response: { task_id: 'old-task' } }, 'approved', ' 已核对 ');
  assert.deepEqual(payload, { decision: 'approved', expected_version: 4, comment: '已核对' });
  const external = domain.buildFollowUpReviewRequest({ ...record, current_evidence: { source: 'external_form' }, effective_response: { task_id: 'task-1', response_id: 42 } }, 'returned', '补充');
  assert.equal(external.evidence.task_id, 'task-1');
});

test('conflicting manual and external current sources are detected for approval blocking', () => {
  assert.equal(domain.hasConflictingFollowUpSources({ ...record, current_evidence: { source: 'manual_entry', legacy: true }, completion_data: { source: 'manual_entry' }, effective_response: { task_id: 'task-1' } }), true);
  assert.equal(domain.hasConflictingFollowUpSources({ ...record, current_evidence: { source: 'manual_entry', legacy: true }, completion_data: { source: 'manual_entry' }, effective_response: null }), false);
  assert.equal(domain.hasConflictingFollowUpSources({ ...record, completion_data: null, effective_response: { task_id: 'task-1' } }), false);
});

test('source contract handles resolved legacy records and fails closed for old or ambiguous responses', () => {
  assert.equal(domain.followUpEvidenceSource({ ...record, current_evidence: { source: 'manual_entry', legacy: true }, completion_data: { source: 'manual_entry' } }), 'manual_entry');
  for (const source of ['unknown', 'ambiguous']) assert.equal(domain.followUpEvidenceSource({ ...record, current_evidence: { source } }), source);
  assert.equal(domain.followUpEvidenceSource({ ...record, completion_data: { source: 'manual_entry' } }), 'unknown');
  const html = renderToStaticMarkup(React.createElement(domain.FollowUpReviewEvidence, { record: { ...record, current_evidence: { source: 'ambiguous' }, completion_data: { source: 'manual_entry' }, notes: '不能冒充当前录入', submission_history: [{ submission_id: 'old-1', source: 'manual_entry', submitted_version: 2, snapshot: { follow_up_result: '历史结果', notes: '历史备注' } }] }, task: null }));
  assert.ok(html.includes('当前不能批准'));
  assert.ok(html.includes('历史结果'));
  assert.ok(html.includes('历史备注'));
  assert.equal(html.includes('不能冒充当前录入'), false);
});

test('re-evaluation matches eligible server states and refuses successor forks or patient actors', () => {
  const { readFileSync } = require('node:fs');
  const service = readFileSync(path.resolve(__dirname, '../../backend/app/services/followup_service.py'), 'utf8');
  const serverStates = [...service.match(/_REEVALUABLE_STATUSES = \{([^}]+)\}/)[1].matchAll(/"([^"]+)"/g)].map(match => match[1]);
  const actor = { id: 'doctor-1', role: 'doctor' };
  for (const state of ['pending_schedule', 'scheduled', 'awaiting_fill', 'in_review', 'completed', 'canceled', 'missed', 'overdue', 'lost', 'rescheduled'].map(value => ({ value }))) {
    assert.equal(domain.canReEvaluateFollowUp({ ...record, status: state.value }, actor), serverStates.includes(state.value), state.value);
  }
  for (const next of [{ next_visit_id: 'new-1' }, { next_follow_up_id: 'old-1' }]) assert.equal(domain.canReEvaluateFollowUp({ ...record, status: 'completed', ...next }, actor), false);
  assert.equal(domain.canReEvaluateFollowUp({ ...record, status: 'completed' }, { id: 'doctor-1', role: 'patient' }), false);
  assert.equal(domain.canReEvaluateFollowUp({ ...record, status: 'completed' }, { id: 'manager-1', role: 'health_manager' }), true);
});
test('visit details display exact previous and successor links, including legacy next id', () => {
  const html = renderToStaticMarkup(React.createElement(domain.FollowUpVisitLinks, { record: { ...record, previous_visit_id: 'prior-1', next_follow_up_id: 'next-legacy' }, onOpen() {} }));
  for (const value of ['prior-1', 'next-legacy', '查看前次访视', '查看后继访视', '不能重复发起复评']) assert.ok(html.includes(value), value);
});
test('list offers re-evaluation only for eligible nodes and clearly identifies existing successors', () => {
  const list = overrides => renderToStaticMarkup(React.createElement(domain.FollowUpList, { records: [{ ...record, status: 'completed', ...overrides }], onView() {}, onReEvaluate() {}, canReEvaluate: entry => domain.canReEvaluateFollowUp(entry, { id: 'doctor-1', role: 'doctor' }) }));
  assert.ok(list({}).includes('发起复评'));
  const linked = list({ next_visit_id: 'child-1' });
  assert.ok(linked.includes('已有后继节点'));
  assert.equal(linked.includes('发起复评'), false);
  assert.equal(list({ status: 'lost' }).includes('发起复评'), false);
});
