// T72 康复处方结构化与签署前端逻辑测试（Node 内置 test runner，esbuild 编译 utils 模块）。
const assert = require('node:assert/strict');
const { test } = require('node:test');
const path = require('node:path');
const Module = require('node:module');
const { buildSync } = require('esbuild');
const filename = path.join(__dirname, '.rehab-prescription-workbench.compiled.cjs');
const code = buildSync({ entryPoints: [path.resolve(__dirname, '../src/utils/rehabClinicalWorkbench.ts')], bundle: true, platform: 'node', format: 'cjs', write: false }).outputFiles[0].text;
const loaded = new Module(filename, module); loaded.filename = filename; loaded.paths = Module._nodeModulePaths(__dirname); loaded._compile(code, filename);
const { findingLines, validateItems, workbenchError, contentPayload } = loaded.exports;

test('findingLines renders block findings first with the declared review status', () => {
  const report = {
    warnings: [{ rule_id: 'w1', level: 'warn', message: '运动强度请核实', status: '待临床确认' }],
    blocks: [{ rule_id: 'b1', level: 'block', message: '过敏史冲突，发布被阻断', status: '待临床确认' }],
  };
  const lines = findingLines(report);
  assert.deepEqual(lines, ['【阻断】过敏史冲突，发布被阻断（待临床确认）', '【提示】运动强度请核实（待临床确认）']);
  assert.deepEqual(findingLines(null), []);
  assert.deepEqual(findingLines({ warnings: [], blocks: [] }), []);
  // 缺失或空白 message 的 finding 不渲染
  assert.deepEqual(findingLines({ blocks: [{ level: 'block', message: '  ' }] }), []);
});

test('validateItems trims execution requirements and drops empty course payloads', () => {
  const items = validateItems([
    { intervention_type: 'exercise', name: ' 股四头肌训练 ', description: ' ', course: { duration_days: 14, sessions_total: null, note: ' 两周复评 ' },
      execution_requirements: [' 每周复评 ', '', '  '] },
    { intervention_type: 'exercise', name: '平地步行', course: { duration_days: null, sessions_total: null, note: '   ' }, execution_requirements: [] },
  ]);
  assert.equal(items[0].name, '股四头肌训练');
  assert.equal(items[0].description, null);
  assert.deepEqual(items[0].course, { duration_days: 14, sessions_total: null, note: '两周复评' });
  assert.deepEqual(items[0].execution_requirements, ['每周复评']);
  // 全空的疗程与执行要求归一为 null（后端把空疗程视为无信息）
  assert.equal(items[1].course, null);
  assert.equal(items[1].execution_requirements, null);
  assert.throws(() => validateItems([{ intervention_type: 'exercise', name: ' ' }]));
});

test('workbenchError surfaces structured backend messages such as contraindication blocks', () => {
  const blocked = { response: { status: 422, data: { detail: { error: 'REHAB_CONTRAINDICATION_BLOCK',
    message: '存在禁忌阻断项，发布被拒绝：患者过敏史冲突', details: { findings: [{ rule_id: 'r1' }] } } } } };
  assert.equal(workbenchError(blocked, 'fallback'), '存在禁忌阻断项，发布被拒绝：患者过敏史冲突');
  assert.equal(workbenchError({ response: { status: 422, data: { detail: '纯文本 422' } } }, 'fallback'), '纯文本 422');
  assert.equal(workbenchError({ response: { status: 409 } }, 'fallback'), '方案已更新或本次操作发生冲突。请重新加载核对后再操作。');
  assert.equal(workbenchError({}, 'fallback'), 'fallback');
});

test('contentPayload keeps requiring the published content contract', () => {
  assert.throws(() => contentPayload({ name: '', description: 'd', goal: 'g', start_date: '', end_date: '', frequency: '', patient_instructions: '' }));
  const payload = contentPayload({ name: '方案', description: '说明', goal: '目标', start_date: '2026-11-15T08:00:00',
    end_date: '', frequency: ' ', patient_instructions: '' });
  assert.equal(payload.frequency, null);
  assert.equal(payload.patient_instructions, null);
  assert.ok(payload.start_date.endsWith('Z'));
});
