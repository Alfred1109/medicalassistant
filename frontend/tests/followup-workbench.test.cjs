const assert = require('node:assert/strict');
const { test } = require('node:test');
const path = require('node:path');
const Module = require('node:module');
const { buildSync } = require('esbuild');
const filename = path.join(__dirname, '.followup-workbench.compiled.cjs');
const code = buildSync({ entryPoints: [path.resolve(__dirname, '../src/utils/followupWorkbench.ts')], bundle: true, platform: 'node', format: 'cjs', write: false }).outputFiles[0].text;
const loaded = new Module(filename, module); loaded.filename = filename; loaded.paths = Module._nodeModulePaths(__dirname); loaded._compile(code, filename);
const { buildFollowUpWorkbenchQuery: query, localDayBoundary } = loaded.exports;

test('workbench sends server paging and all filters without patient fan-out', () => {
  const result = query('all', { status: 'in_review', follow_up_type: 'phone', patient_name: ' 张三 ' }, 2, 25);
  assert.deepEqual(result, { patient_id: undefined, status: 'in_review', follow_up_type: 'phone', start_date: undefined, end_date: undefined, patient_name: '张三', skip: 50, limit: 25 });
  assert.equal(query('patient-2', {}, 0, 10).patient_id, 'patient-2');
  for (const args of [['all', {}, -1, 10], ['all', {}, 1.5, 10], ['all', {}, 0, 101], ['all', { start_date: '2026-12-02', end_date: '2026-12-01' }, 0, 10]]) assert.throws(() => query(...args));
});

test('calendar filters use local midnight and an exclusive next calendar day, including DST', () => {
  const previous = process.env.TZ;
  try {
    process.env.TZ = 'Asia/Singapore';
    const result = query('all', { start_date: '2026-11-09', end_date: '2026-11-09' }, 0, 10);
    assert.equal(result.start_date, '2026-11-08T16:00:00.000Z');
    assert.equal(result.end_date, '2026-11-09T16:00:00.000Z');
    process.env.TZ = 'America/New_York';
    assert.equal(localDayBoundary('2026-03-08'), '2026-03-08T05:00:00.000Z');
    assert.equal(localDayBoundary('2026-03-08', true), '2026-03-09T04:00:00.000Z');
    assert.equal(localDayBoundary('2026-11-01'), '2026-11-01T04:00:00.000Z');
    assert.equal(localDayBoundary('2026-11-01', true), '2026-11-02T05:00:00.000Z');
    for (const bad of ['2026-02-30', '2026-13-01', 'invalid', '2026-1-1']) assert.throws(() => localDayBoundary(bad));
  } finally { if (previous === undefined) delete process.env.TZ; else process.env.TZ = previous; }
});
