const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const { transformSync } = require('esbuild');

const root = path.resolve(__dirname, '..');
const loadService = (transport) => {
  const file = path.resolve(root, 'src/services/patientAccountBindings.ts');
  const compiled = new Module(file, module);
  compiled.filename = file;
  compiled.paths = Module._nodeModulePaths(__dirname);
  compiled.require = name => name === './httpClient' ? transport : require(name);
  compiled._compile(transformSync(fs.readFileSync(file, 'utf8'), { loader: 'ts', format: 'cjs' }).code, file);
  return compiled.exports;
};

test('binding service posts create/disable to the T64 admin-only endpoints with audit payloads', async () => {
  const calls = [];
  const transport = { post: async (...args) => { calls.push(args); return { data: {} }; } };
  const { patientAccountBindingService } = loadService(transport);
  await patientAccountBindingService.createBinding({
    patient_id: 'patient-1', account_id: 'a'.repeat(24),
    reviewer: '管理员', evidence_reference: 'EVD-001',
  });
  await patientAccountBindingService.disableBinding('patient-1', {
    reviewer: '管理员', evidence_reference: 'EVD-002',
  });
  assert.deepEqual(calls, [
    ['/patients/account-bindings', {
      patient_id: 'patient-1', account_id: 'a'.repeat(24),
      reviewer: '管理员', evidence_reference: 'EVD-001',
    }],
    ['/patients/account-bindings/patient-1/disable', { reviewer: '管理员', evidence_reference: 'EVD-002' }],
  ]);
});

test('domain errors are translated fail-closed with the mutual-exclusion rule stated', () => {
  const { accountBindingErrorCopy } = loadService({});
  assert.match(accountBindingErrorCopy({
    response: { data: { detail: { error: 'PATIENT_ACCOUNT_LINK_CONFLICT', message: 'conflict' } } },
  }), /不做隐式替换/);
  assert.match(accountBindingErrorCopy({
    response: { data: { detail: { error: 'PATIENT_REVIEW_REQUIRED', message: 'review' } } },
  }), /人工核实/);
  assert.match(accountBindingErrorCopy({
    response: { data: { detail: { error: 'PATIENT_DOMAIN_STATE_UNAVAILABLE', message: 'down' } } },
  }), /不可用|稍后/);
  assert.equal(accountBindingErrorCopy(new Error('network down')), 'network down');
});

test('the admin page, route and menu expose account bindings distinctly from patient-links', () => {
  const page = fs.readFileSync(path.join(root, 'src/pages/Admin/AccountBindings.tsx'), 'utf8');
  // 创建需要患者+账号+审核人+凭证；停用需要患者+审核人+凭证
  for (const field of ['patient_id', 'account_id', 'reviewer', 'evidence_reference']) {
    assert.match(page, new RegExp(field));
  }
  assert.match(page, /createBinding/);
  assert.match(page, /disableBinding/);
  // 没有查询端点：页面不得伪造检索面板，且服务不提供任何 GET
  const service = fs.readFileSync(path.join(root, 'src/services/patientAccountBindings.ts'), 'utf8');
  assert.doesNotMatch(service, /\.get\(/);
  assert.match(page, /没有绑定关系查询端点|没有列表\/查询端点/);

  const routes = fs.readFileSync(path.join(root, 'src/routes.tsx'), 'utf8');
  assert.match(routes, /account-bindings/);
  const layout = fs.readFileSync(path.join(root, 'src/components/Layout/Layout.tsx'), 'utf8');
  assert.match(layout, /账号绑定管理/);
  // 与 113.44 的外部问卷关联菜单分开
  assert.match(layout, /患者与问卷来源/);
  assert.match(layout, /\/app\/admin\/account-bindings/);
  assert.match(layout, /\/app\/admin\/patient-links/);
});
