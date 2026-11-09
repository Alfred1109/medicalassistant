const assert = require('node:assert/strict');
const { test } = require('node:test');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const { buildSync, transformSync } = require('esbuild');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

const root = path.resolve(__dirname, '..');
const filename = path.join(__dirname, '.patient-sources.compiled.cjs');
const compiled = buildSync({ stdin: { contents: `export * from './utils/patientLinkReview'; export {PatientLinkConfirmation} from './components/Admin/PatientLinkPanel'; export {FormBindingConfirmation} from './components/Admin/FormBindingPanel';`, resolveDir: path.join(root, 'src'), loader: 'ts' }, bundle: true, platform: 'node', format: 'cjs', write: false, packages: 'external', define: { 'import.meta.env.VITE_API_URL': 'undefined', 'import.meta.env.VITE_API_PREFIX': 'undefined' }, logLevel: 'silent' }).outputFiles[0].text;
const loaded = new Module(filename, module); loaded.filename = filename; loaded.paths = Module._nodeModulePaths(__dirname); loaded._compile(compiled, filename);
const domain = loaded.exports;
const source = { system: 'form-platform-11344', environment: 'production' };
const project = { project_id: 1, name: '合成项目', status: 'active', source };
const center = { center_id: 2, project_id: 1, center_code: 'C2', name: '合成中心', status: 'active' };
const subject = { subject_id: 3, project_id: 1, center_id: 2, code: 'S3', status: 'enrolled' };
const reference = { source, project_id: 1, center_id: 2, subject_id: 3, patient_id: 4, patient_archive_id: 5 };
const input = { localPatientId: 'patient-1', project, center, subject, reference, evidenceReference: ' 核验记录-1 ', identityVerified: true };
const form = { form_id: 8, project_id: 1, title: '合成问卷', status: 'active', current_version: { form_id: 8, family_id: 7, version: 2, version_state: 'current', definition_sha256: 'a'.repeat(64) } };

test('patient association only carries exact reviewed identifiers and evidence', () => {
  assert.deepEqual(domain.buildPatientLinkReview(input), { local_patient_id: 'patient-1', project_id: 1, center_id: 2, subject_id: 3, evidence_reference: '核验记录-1', identity_verified: true });
  for (const change of [{ localPatientId: '' }, { identityVerified: false }, { evidenceReference: ' ' }, { evidenceReference: 'a'.repeat(257) }, { reference: null }]) assert.throws(() => domain.buildPatientLinkReview({ ...input, ...change }));
});

test('changed project, center, subject and source environment fail closed', () => {
  for (const change of [
    { center: { ...center, project_id: 99 } }, { subject: { ...subject, center_id: 99 } },
    { subject: { ...subject, project_id: 99 } }, { reference: { ...reference, project_id: 99 } },
    { reference: { ...reference, subject_id: 99 } }, { reference: { ...reference, center_id: 99 } },
    { reference: { ...reference, source: { ...source, environment: 'pilot' } } },
  ]) assert.throws(() => domain.buildPatientLinkReview({ ...input, ...change }));
});

test('additional project context requires same patient and a new explicit context', () => {
  const link = { id: 'link-1', local_patient_id: 'patient-1', status: 'verified', reference, references: [reference] };
  assert.equal(domain.canAddPatientContext(link, reference), false);
  const next = { ...reference, project_id: 11, center_id: 12, subject_id: 13 };
  const nextInput = { ...input, project: { ...project, project_id: 11 }, center: { ...center, project_id: 11, center_id: 12 }, subject: { ...subject, project_id: 11, center_id: 12, subject_id: 13 }, reference: next };
  assert.equal(domain.canAddPatientContext(link, next), true);
  assert.deepEqual(domain.buildPatientContextReview(link, nextInput), { project_id: 11, center_id: 12, subject_id: 13, evidence_reference: '核验记录-1', identity_verified: true });
  for (const bad of [{ ...link, status: 'revoked' }, { ...link, reference: { ...reference, patient_id: 999 } }]) assert.equal(domain.canAddPatientContext(bad, next), false);
  assert.throws(() => domain.buildPatientContextReview(link, { ...nextInput, localPatientId: 'different-patient' }));
});

test('form selection requires a current version, explicit purpose and reviewed evidence', () => {
  const proposal = { project, form, purpose: 'followup', evidenceReference: ' SOP-1 ', confirmed: true };
  assert.deepEqual(domain.buildFormBindingReview(proposal), { project_id: 1, form_id: 8, version: 2, purpose: 'followup', evidence_reference: 'SOP-1', confirmed: true });
  for (const change of [{ purpose: '' }, { purpose: 'unknown' }, { confirmed: false }, { evidenceReference: '' }, { evidenceReference: 'x'.repeat(257) },
    { form: { ...form, project_id: 9 } }, { form: { ...form, current_version: null } },
    { form: { ...form, current_version: { ...form.current_version, version_state: 'draft' } } },
    { form: { ...form, current_version: { ...form.current_version, version_state: 'retired' } } },
    { form: { ...form, current_version: { ...form.current_version, definition_sha256: null } } },
  ]) assert.throws(() => domain.buildFormBindingReview({ ...proposal, ...change }));
});

test('confirmation screens show exact records and escape untrusted names', () => {
  const patient = renderToStaticMarkup(React.createElement(domain.PatientLinkConfirmation, { project, center, subject, reference, localPatientId: 'patient-1', localName: '<script>wrong()</script>' }));
  for (const text of ['patient-1', 'S3', '患者档案编号', '&lt;script&gt;', '不会变更现有医护分配']) assert.ok(patient.includes(text), text);
  assert.equal(patient.includes('<script>'), false);
  const html = renderToStaticMarkup(React.createElement(domain.FormBindingConfirmation, { project, form, purpose: 'followup' }));
  for (const text of ['合成问卷', '正式版本', '随访', '仍需核验中心']) assert.ok(html.includes(text), text);
  assert.equal(html.includes(form.current_version.definition_sha256), false);
  assert.equal(html.includes('定义摘要'), false);
});

test('actual API adapters use reviewed catalog, metadata and explicit mutation paths', async () => {
  const calls = [];
  const transport = Object.fromEntries(['get', 'post'].map(method => [method, async (...args) => { calls.push({ method, args }); return { data: {} }; }]));
  const file = path.join(root, 'src/services/formCatalog.ts');
  const service = new Module(file, module); service.filename = file; service.paths = Module._nodeModulePaths(__dirname);
  service.require = name => name === './httpClient' ? transport : require(name);
  service._compile(transformSync(readFileSync(file, 'utf8'), { loader: 'ts', format: 'cjs' }).code, file);
  const api = service.exports.formCatalog;
  await api.projects({ cursor: 'opaque_cursor' });
  await api.subjects(1, 2, { limit: 20 });
  await api.patientReference(1, 2, 3);
  await api.formVersion(1, 8);
  await api.createLink(domain.buildPatientLinkReview(input));
  await api.addLinkContext('link-1', { project_id: 11, center_id: 12, subject_id: 13, evidence_reference: 'review', identity_verified: true });
  await api.revokeLink('link-1', 'wrong reference');
  await api.createFormBinding(domain.buildFormBindingReview({ project, form, purpose: 'followup', evidenceReference: 'SOP-1', confirmed: true }));
  assert.deepEqual(calls.map(c => [c.method, c.args[0]]), [
    ['get', '/integrations/forms/catalog/projects'], ['get', '/integrations/forms/catalog/projects/1/subjects'],
    ['get', '/integrations/forms/catalog/projects/1/centers/2/subjects/3/patient-reference'], ['get', '/integrations/forms/catalog/projects/1/forms/8/version'],
    ['post', '/integrations/forms/patient-links'], ['post', '/integrations/forms/patient-links/link-1/contexts'],
    ['post', '/integrations/forms/patient-links/link-1/revoke'], ['post', '/integrations/forms/form-bindings'],
  ]);
  assert.deepEqual(calls[1].args[1].params, { limit: 20, center_id: 2, status: 'all' });
  assert.equal(calls.some(c => /fill-tasks|embed/.test(c.args[0])), false);
});
