const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const { transformSync } = require('esbuild');

const root = path.resolve(__dirname, '..');
const load = (relative, replacements) => {
  const file = path.resolve(root, 'src', relative);
  const compiled = new Module(file, module);
  compiled.filename = file;
  compiled.paths = Module._nodeModulePaths(__dirname);
  compiled.require = name => name in replacements ? replacements[name] : require(name);
  compiled._compile(transformSync(fs.readFileSync(file, 'utf8'), { loader: 'ts', format: 'cjs' }).code, file);
  return compiled.exports;
};
const loadService = (transport) => load('services/planVersionHistory.ts', { './httpClient': transport });

test('version service hits the REH01 object-scoped endpoints with server contracts', async () => {
  const calls = [];
  const transport = { get: async (...args) => { calls.push(args); return { data: [] }; } };
  const { planVersionService } = loadService(transport);
  await planVersionService.listVersions('plan-1');
  await planVersionService.listItems('plan-1', 'version-9');
  await planVersionService.getVersion('plan-1', 'version-9');
  assert.deepEqual(calls, [
    ['/rehabilitation/plans/plan-1/versions', { params: { limit: 100 } }],
    ['/rehabilitation/plans/plan-1/items', { params: { version_id: 'version-9', limit: 200 } }],
    ['/rehabilitation/plans/plan-1/versions/version-9'],
  ]);
});

test('snapshot diff reports per-field changes against an empty baseline', () => {
  const { diffSnapshotFields } = loadService({});
  const base = { name: ' knee plan ', goal: 'recover' };
  const target = { name: 'knee plan', goal: 'recover', frequency: 'daily' };
  const diffs = diffSnapshotFields(base, target);
  assert.equal(diffs.length, 8); // 白名单 8 个字段全部呈现
  const byField = Object.fromEntries(diffs.map(d => [d.field, d]));
  assert.equal(byField.name.changed, true);
  assert.equal(byField.goal.changed, false);
  assert.equal(byField.frequency.changed, true);
  assert.equal(byField.start_date.baseValue, '（空）');
  assert.equal(byField.end_date.targetValue, '（空）');
});

test('prescription item diff keys on the stable item_id and ignores version ownership', () => {
  const { diffPrescriptionItems } = loadService({});
  const base = [
    { item_id: 'a'.repeat(24), name: 'walk', intervention_type: 'exercise', version_id: 'v1' },
    { item_id: 'b'.repeat(24), name: 'ibuprofen', intervention_type: 'medication', version_id: 'v1', dosage: { value: 1 } },
  ];
  const target = [
    { item_id: 'a'.repeat(24), name: 'walk', intervention_type: 'exercise', version_id: 'v2' },
    { item_id: 'b'.repeat(24), name: 'ibuprofen', intervention_type: 'medication', version_id: 'v2', dosage: { value: 2 } },
    { item_id: 'c'.repeat(24), name: 'diet plan', intervention_type: 'diet', version_id: 'v2' },
  ];
  const diff = diffPrescriptionItems(base, target);
  assert.deepEqual(diff.added.map(e => e.item_id), ['c'.repeat(24)]);
  assert.deepEqual(diff.changed.map(e => e.item_id), ['b'.repeat(24)]);
  assert.deepEqual(diff.removed, []);
  assert.equal(diff.unchangedCount, 1);

  const reversed = diffPrescriptionItems(target, base);
  assert.deepEqual(reversed.added, []);
  assert.deepEqual(reversed.changed.map(e => e.item_id), ['b'.repeat(24)]);
  assert.deepEqual(reversed.removed.map(e => e.item_id), ['c'.repeat(24)]);
  assert.equal(reversed.unchangedCount, 1);
});

test('the workbench exposes read-only version history entries wired to the dialog', () => {
  const workbench = fs.readFileSync(path.join(root, 'src/pages/RehabPlan/ClinicianPlanWorkbench.tsx'), 'utf8');
  assert.match(workbench, /PlanVersionHistoryDialog/);
  assert.match(workbench, /版本历史/);
  // 入口只在医护端工作台（角色守卫页面），不向患者视图暴露编辑语义
  assert.doesNotMatch(workbench, /创建方案版本|create_plan_version/);
  const dialog = fs.readFileSync(path.join(root, 'src/components/Rehabilitation/PlanVersionHistoryDialog.tsx'), 'utf8');
  assert.match(dialog, /version_no/);
  assert.match(dialog, /变更摘要/);
  // 版本历史是只读历史：不允许出现对版本的写请求
  assert.doesNotMatch(dialog, /\.post\(|\.put\(|\.delete\(/);
});
