const assert = require('node:assert/strict');
const { test } = require('node:test');
const Module = require('node:module');
const path = require('node:path');
const { buildSync } = require('esbuild');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

const filename = path.resolve(__dirname, '.followup-notifications.compiled.cjs');
const compiled = buildSync({
  stdin: { contents: `export * from './utils/notificationTarget'; export {FollowUpReadOnlySummary} from './pages/FollowUpDetailPage';`,
    resolveDir: path.resolve(__dirname, '../src'), loader: 'ts' },
  bundle: true, platform: 'node', format: 'cjs', write: false, packages: 'external',
  define: { 'import.meta.env.VITE_API_URL': 'undefined', 'import.meta.env.VITE_API_PREFIX': 'undefined' }, logLevel: 'silent',
}).outputFiles[0].text;
const loaded = new Module(filename, module); loaded.filename = filename; loaded.paths = Module._nodeModulePaths(__dirname);
loaded._compile(compiled, filename);
const domain = loaded.exports;
const id = '507f1f77bcf86cd799439011';
const notification = { notification_type: 'followup', related_entity_type: 'followup', related_entity_id: id };

test('only known followup identities and supported roles select a fixed internal route', () => {
  for (const role of ['patient', 'doctor', 'health_manager', 'admin']) {
    assert.equal(domain.notificationTarget(notification, role), `/app/follow-ups/${id}`);
    assert.equal(domain.canReadFollowUp(role), true);
  }
  for (const role of [undefined, '', 'unknown']) {
    assert.equal(domain.notificationTarget(notification, role), null);
    assert.equal(domain.canReadFollowUp(role), false);
  }
  for (const change of [{ notification_type: 'message' }, { related_entity_type: 'url' },
    { related_entity_id: 'https://attacker.invalid' }, { related_entity_id: '../another-route' },
    { related_entity_id: id + '?admin=true' }, { related_entity_id: null }]) {
    assert.equal(domain.notificationTarget({ ...notification, ...change }, 'patient'), null);
  }
  assert.equal(domain.notificationTarget({ ...notification, related_entity_id: id.toUpperCase(), url: 'https://attacker.invalid' }, 'patient'), `/app/follow-ups/${id}`);
});

test('detail errors identify unavailable authorization without exposing server payloads', () => {
  const error = status => ({ response: { status, data: { detail: 'sensitive content' } } });
  assert.match(domain.followUpDetailError(error(401)), /重新登录/);
  assert.match(domain.followUpDetailError(error(403)), /无权/);
  assert.match(domain.followUpDetailError(error(404)), /不存在或已移除/);
  assert.equal(domain.followUpDetailError(error(500)).includes('sensitive content'), false);
});

test('BSON UTC timestamps render in the selected local timezone with explicit offsets', () => {
  const date = '2026-11-09T00:30:00';
  const singapore = domain.formatFollowUpSchedule(date, 'Asia/Singapore');
  assert.match(singapore, /08:30:00/);
  assert.match(singapore, /UTC\+08:00/);
  assert.equal(singapore, domain.formatFollowUpSchedule(date + 'Z', 'Asia/Singapore'));
  assert.equal(singapore, domain.formatFollowUpSchedule('2026-11-09T08:30:00+08:00', 'Asia/Singapore'));
  const winter = domain.formatFollowUpSchedule(date, 'America/New_York');
  const summer = domain.formatFollowUpSchedule('2026-07-09T00:30:00Z', 'America/New_York');
  assert.match(winter, /19:30:00/); assert.match(winter, /UTC-05:00/);
  assert.match(summer, /20:30:00/); assert.match(summer, /UTC-04:00/);
  for (const invalid of ['not-a-date', '2026-14-09T00:30:00', '2026-11-09']) {
    assert.equal(domain.formatFollowUpSchedule(invalid), invalid + '（原始时间，未转换）');
  }
  assert.equal(domain.formatFollowUpSchedule(''), '未提供');
});

test('default timezone follows the browser environment instead of fixing UTC plus eight', () => {
  const previous = process.env.TZ;
  try {
    for (const timezone of ['Asia/Singapore', 'America/New_York']) {
      process.env.TZ = timezone;
      assert.equal(domain.formatFollowUpSchedule('2026-11-09T00:30:00'),
        domain.formatFollowUpSchedule('2026-11-09T00:30:00', timezone));
    }
  } finally {
    if (previous === undefined) delete process.env.TZ; else process.env.TZ = previous;
  }
});

test('read-only summary escapes text and excludes clinical evidence and review controls', () => {
  const record = { id, status: 'scheduled', follow_up_type: 'phone', scheduled_date: '2026-11-09T00:30:00Z',
    description: '<script>unsafe()</script>', notes: 'private note', answers: [{ answer_text: 'private answer' }],
    review: { history: [{ comment: 'private review' }] }, effective_response: { response_id: 'secret-reference' } };
  const html = renderToStaticMarkup(React.createElement(domain.FollowUpReadOnlySummary, { record }));
  assert.match(html, /随访方式/);
  assert.match(html, /计划时间/);
  assert.match(html, /&lt;script&gt;/);
  for (const text of ['<script>', 'private note', 'private answer', 'private review', 'secret-reference', '批准', '发起复评']) {
    assert.equal(html.includes(text), false, text);
  }
});
