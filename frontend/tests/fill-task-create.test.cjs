const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

test('creating a task preserves the reviewed source and linked follow-up', async () => {
  const calls = [];
  const filename = path.resolve(__dirname, '../src/services/formIntegrationService.ts');
  const compiled = ts.transpileModule(readFileSync(filename, 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, esModuleInterop: true },
  });
  const module = { exports: {} };
  vm.runInNewContext(compiled.outputText, {
    module, exports: module.exports, URL,
    require(name) {
      assert.equal(name, './apiClient');
      return { async post(url, body) { calls.push({ url, body }); return { id: 'task' }; } };
    },
  }, { filename });
  const task = await module.exports.formIntegrationService.createFillTask({
    patientId: 'patient', remoteProjectId: 6, remoteCenterId: 5, remoteSubjectId: 4,
    remoteQuestionnaireId: 56, formBindingId: 'binding', formPurpose: 'followup',
    allowedOrigin: 'https://119.45.42.217', followupVisitId: 'followup', visitCode: 'visit',
  });
  assert.equal(task.id, 'task');
  assert.equal(calls[0].url, '/integrations/forms/fill-tasks');
  assert.equal(calls[0].body.patient_id, 'patient');
  assert.equal(calls[0].body.form_binding_id, 'binding');
  assert.equal(calls[0].body.form_purpose, 'followup');
  assert.equal(calls[0].body.followup_visit_id, 'followup');
  assert.equal(calls[0].body.visit_code, 'visit');
  assert.equal(calls[0].body.remote_questionnaire_id, 56);
});
