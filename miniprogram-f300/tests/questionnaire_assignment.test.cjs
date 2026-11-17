const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

test('staff explicitly assigns a patient self-fill task using reviewed selectors', async () => {
  let page;
  const calls = [];
  const session = { identityConfirmed: true, role: 'doctor', sessionId: 1, user: { id: 'doctor' } };
  const api = { getSession: () => session, request: async (url, options = {}) => {
    calls.push({ url, options });
    return options.method === 'POST' ? { id: 'task' } : { items: [], total: 0 };
  } };
  const context = { URL, wx: {}, Page(value) { page = value; }, require(name) {
    if (name === '../../../services/api') return api;
    if (name === '../../../config') return { apiBaseUrl: 'https://care.example/api' };
    throw Error(name);
  } };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../miniprogram/pages/clinical/tasks/index.js'), 'utf8'), context);
  page.data = { ...page.data, taskMode: 'patient', patientIndex: 0, referenceIndex: 0, formIndex: 0,
    candidates: [{ patient_id: 'patient', references: [{ project_id: 1, center_id: 2, subject_id: 3,
      forms: [{ form_id: 4, binding_id: 'binding', purpose: 'followup' }] }] }],
    followupOptions: [{ id: '' }], followupIndex: 0 };
  page.setData = update => Object.assign(page.data, update);
  page._identityKey = 'doctor:doctor:1'; page._generation = 0;
  await page.createTask();
  assert.equal(calls[0].url, '/integrations/forms/patient-self/tasks');
  assert.equal(calls[0].options.data.patient_id, 'patient');
  assert.equal(calls[0].options.data.remote_subject_id, 3);
  assert.equal(calls[0].options.data.remote_questionnaire_id, 4);
  assert.equal(calls[0].options.data.form_binding_id, 'binding');
  assert.equal(calls[0].options.data.subject_id, undefined);
});
