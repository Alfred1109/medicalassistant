const assert = require('node:assert/strict');
const test = require('node:test');
const path = require('node:path');
const Module = require('node:module');
const { buildSync } = require('esbuild');
const { format } = require('date-fns');
const { zhCN } = require('date-fns/locale');
const filename = path.join(__dirname, '.date-time.compiled.cjs');
const code = buildSync({ entryPoints: [path.resolve(__dirname, '../src/utils/dateTime.ts')], bundle: true,
  platform: 'node', format: 'cjs', write: false }).outputFiles[0].text;
const loaded = new Module(filename, module); loaded.filename = filename;
loaded.paths = Module._nodeModulePaths(__dirname); loaded._compile(code, filename);
const { formatAppDate } = loaded.exports;

function inZone(zone, run) {
  const previous = process.env.TZ;
  process.env.TZ = zone;
  try { run(); } finally { if (previous === undefined) delete process.env.TZ; else process.env.TZ = previous; }
}

test('display patterns preserve local calendar dates, native parsing and locale output', () => {
  for (const zone of ['Asia/Singapore', 'America/Los_Angeles']) inZone(zone, () => {
    const instant = new Date('2026-11-09T00:30:12Z');
    assert.equal(formatAppDate(instant, 'minute'), format(instant, 'yyyy-MM-dd HH:mm'));
    assert.equal(formatAppDate(instant, 'locale'), instant.toLocaleString());
    assert.equal(formatAppDate(instant, 'localeZh24'), instant.toLocaleString('zh-CN', { hour12: false }));
    assert.equal(formatAppDate(instant, 'localeDay'), instant.toLocaleDateString());
    assert.equal(formatAppDate(instant, 'localeTime'), instant.toLocaleTimeString());
    assert.equal(formatAppDate(instant, 'MM月dd日'), format(instant, 'MM月dd日', { locale: zhCN }));
    // Calendar dates stay local; the explicitly selected native mode retains JS Date parsing.
    assert.equal(formatAppDate('2026-11-09', 'yyyy-MM-dd'), '2026-11-09');
    assert.equal(formatAppDate('2026-11-09', 'yyyy-MM-dd', { parse: 'native' }), format(new Date('2026-11-09'), 'yyyy-MM-dd'));
  });
});

test('BSON UTC without suffix and explicit offsets retain timestamp semantics', () => inZone('Asia/Singapore', () => {
  assert.equal(formatAppDate('2026-11-09T00:30:00', 'minute', { assumeUtc: true }), '2026-11-09 08:30');
  assert.equal(formatAppDate('2026-11-09T00:30:00', 'minute'), '2026-11-09 00:30');
  for (const suffix of ['Z', '+00:00', '+0000']) {
    assert.equal(formatAppDate(`2026-11-09T00:30:00${suffix}`, 'minute', { assumeUtc: true }), '2026-11-09 08:30');
  }
  const zoned = formatAppDate('2026-11-09T00:30:00', 'zoned', { assumeUtc: true, timeZone: 'Asia/Singapore' });
  assert.match(zoned, /08:30:00/);
  assert.match(zoned, /UTC\+08:00/);
  assert.equal(formatAppDate('2026-11-09T00:30:12.123', "yyyy-MM-dd'T'HH:mm:ss.SSS", { assumeUtc: true, parse: 'native' }), '2026-11-09T08:30:12.123');
}));

test('empty and invalid values retain caller-specific evidence and fallback copy', () => {
  assert.equal(formatAppDate(undefined, 'minute', { empty: '未记录', invalid: '无效' }), '未记录');
  assert.equal(formatAppDate('', 'minute', { empty: '未记录' }), '未记录');
  assert.equal(formatAppDate('bad', 'localeZh24', { invalid: 'bad（原始时间）' }), 'bad（原始时间）');
  assert.equal(formatAppDate(new Date(NaN), 'minute', { invalid: '无效' }), '无效');
  assert.equal(formatAppDate('2026-11-09', 'invalid-format', { invalid: '无效' }), '无效');
});

test('notification display keeps elapsed-day thresholds and local clock', () => inZone('Asia/Singapore', () => {
  const options = { now: new Date('2026-11-15T10:00:00Z') };
  assert.equal(formatAppDate('2026-11-15T09:00:00Z', 'notification', options), '今天 17:00');
  assert.equal(formatAppDate('2026-11-14T09:00:00Z', 'notification', options), '昨天 17:00');
  assert.equal(formatAppDate('2026-11-12T09:00:00Z', 'notification', options), '3天前');
  assert.equal(formatAppDate('2026-11-01T09:00:00Z', 'notification', options), '2026-11-01');
}));
