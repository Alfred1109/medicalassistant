const assert = require('node:assert/strict');
const { test } = require('node:test');
const path = require('node:path');
const Module = require('node:module');
const { buildSync } = require('esbuild');
const filename = path.join(__dirname, '.followup-disposition.compiled.cjs');
const code = buildSync({ entryPoints: [path.resolve(__dirname, '../src/constants/followup.ts')], bundle: true, platform: 'node', format: 'cjs', write: false }).outputFiles[0].text;
const loaded = new Module(filename, module); loaded.filename = filename; loaded.paths = Module._nodeModulePaths(__dirname); loaded._compile(code, filename);
const { getFollowUpStatusBadge: badge, getFollowUpSummaryRows: summaryRows, getOverdueMarker, getLostMarker } = loaded.exports;

const record = (status, metadata) => ({ status, metadata });

test('overdue badge distinguishes automated and manual marking sources', () => {
  assert.equal(badge(record('overdue', { overdue: { source: 'automated', operator_id: null } })).label, '已逾期（系统自动）');
  assert.equal(badge(record('overdue', { overdue: { operator_id: 'doc-1' } })).label, '已逾期（手工标记）');
  // 存量手工标记无 source 字段，按 operator_id 视为手工
  assert.equal(badge(record('overdue', { overdue: { marked_at: 'x', operator_id: 'doc-1' } })).label, '已逾期（手工标记）');
  // 无标记或标记异常时回退通用状态文案
  assert.equal(badge(record('overdue', null)).label, '已逾期');
  assert.equal(badge(record('overdue', { overdue: {} })).label, '已逾期');
});

test('lost badge distinguishes automated and manual recognition, non-disposition states unchanged', () => {
  assert.equal(badge(record('lost', { lost: { source: 'automated', recognized_by: null } })).label, '已失访（系统自动认定）');
  assert.equal(badge(record('lost', { lost: { recognized_by: 'doc-2' } })).label, '已失访（人工认定）');
  assert.equal(badge(record('lost', null)).label, '已失访');
  // 恢复痕迹不影响徽章归类，仅在详情页提示
  assert.equal(badge(record('lost', { lost: { source: 'automated', restored_at: 'x' } })).label, '已失访（系统自动认定）');
  assert.equal(badge(record('completed', null)).label, '已完成');
  assert.equal(badge(record('scheduled', null)).color, 'primary');
});

test('markers are read defensively from arbitrary metadata payloads', () => {
  assert.deepEqual(getOverdueMarker(null), null);
  assert.deepEqual(getLostMarker({ lost: 'garbage' }), null);
  assert.deepEqual(getLostMarker({ lost: { source: 'automated' } }), { source: 'automated' });
});

test('summary rows keep conclusion and optional fields, empty summaries produce nothing', () => {
  assert.deepEqual(summaryRows(null), []);
  assert.deepEqual(summaryRows(undefined), []);
  assert.deepEqual(summaryRows({ conclusion: '  ' }), []);
  const rows = summaryRows({
    conclusion: '血压控制平稳', next_plan_suggestion: '两周后复访', abnormal_findings: '夜间心率偏高',
    recorded_by: 'doc-1', recorded_at: '2026-11-15T00:00:00',
  });
  assert.deepEqual(rows, [
    { label: '结论', value: '血压控制平稳' },
    { label: '下次计划建议', value: '两周后复访' },
    { label: '异常记录', value: '夜间心率偏高' },
  ]);
  // 仅结论的小结也不产生空行
  assert.deepEqual(summaryRows({ conclusion: '结论修订', next_plan_suggestion: null, abnormal_findings: null }),
    [{ label: '结论', value: '结论修订' }]);
});
