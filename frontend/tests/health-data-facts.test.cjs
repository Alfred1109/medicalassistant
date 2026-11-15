const assert = require('node:assert/strict');
const test = require('node:test');
const path = require('node:path');
const Module = require('node:module');
const { buildSync } = require('esbuild');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const filename = path.join(__dirname, '.health-data-facts.compiled.cjs');
const code = buildSync({ stdin: { contents: `export * from './utils/healthDataFacts';
  export * from './utils/healthDataTimeline';
  export { default as QualityNotice } from './components/common/HealthDataQualityNotice';
  export { default as Visualization } from './components/HealthManager/HealthDataVisualization';`,
  resolveDir: path.resolve(__dirname, '../src'), loader: 'ts' },
  bundle: true, packages: 'external', platform: 'node', format: 'cjs', write: false }).outputFiles[0].text;
const loaded = new Module(filename, module); loaded.filename = filename;
loaded.paths = Module._nodeModulePaths(__dirname);
const originalRequire = loaded.require.bind(loaded);
// Match ESM default imports for MUI subpath modules when rendering under Node CJS.
loaded.require = name => {
  const result = originalRequire(name);
  return name.startsWith('@mui/material/') ? result.default ?? result : result;
};
loaded._compile(code, filename);
const domain = loaded.exports;
const fact = (type, value, extra = {}) => ({ id: `${type}-${value}`, patient_id: 'patient-1',
  data_type: 'vital_sign', data_content: { type, value, unit: 'raw-unit' }, source: 'device',
  recorded_at: '2026-11-15T01:02:03', metadata: { device_data_id: 'raw-reading-id', quality_flags: [] }, ...extra });

test('actual HealthDataResponse data_content is consumed and legacy data/vital_type stays compatible', () => {
  const rows = [fact('heart_rate', 71), fact('spo2', 97),
    { id: 'old', data_type: 'vital_sign', data: { vital_type: 'respiratory_rate', value: '18', unit: '次/分' }, recorded_at: '2026-11-15T02:00:00Z' }];
  assert.deepEqual(domain.healthObservations(rows).map(point => [point.type, point.value]),
    [['heart_rate', 71], ['oxygen_saturation', 97], ['respiratory_rate', 18]]);
  assert.equal(domain.healthDataPayload({ ...rows[0], data: { type: 'wrong', value: 999 } }).value, 71);
  assert.deepEqual(domain.healthObservations([{ data_type: 'device_measurement', data_content: { type: 'vendor', value: 2 } }]), []);
});

test('doctor monitoring display fields read vital and lab values from HealthDataResponse.data_content', () => {
  const vital = fact('heart_rate', 71);
  assert.deepEqual(domain.healthDataVitalDisplay(vital), {
    type: 'heart_rate', value: 71, unit: 'raw-unit',
  });

  const lab = { id: 'lab-1', data_type: 'lab_result', data_content: {
    test_name: '空腹血糖', result_value: '6.2', unit: 'mmol/L',
    reference_range: '3.9–6.1', interpretation: '偏高',
  } };
  assert.deepEqual(domain.healthDataLabDisplay(lab), {
    testName: '空腹血糖', value: '6.2', unit: 'mmol/L',
    reference: '3.9–6.1', interpretation: '偏高',
  });
});

test('independent blood-pressure components retain their timestamps without pairing or MAP inference', () => {
  const rows = [fact('systolic_pressure', 120),
    fact('blood_pressure_diastolic', 80, { recorded_at: '2026-11-15T01:08:03Z' }),
    fact('blood_pressure', { systolic: 130, diastolic: 85 }, { recorded_at: '2026-11-15T03:00:00Z' })];
  const points = domain.healthObservations(rows);
  assert.deepEqual(points.map(point => [point.type, point.value, point.timestamp]), [
    ['blood_pressure_systolic', 120, rows[0].recorded_at],
    ['blood_pressure_diastolic', 80, rows[1].recorded_at],
    ['blood_pressure_systolic', 130, rows[2].recorded_at],
    ['blood_pressure_diastolic', 85, rows[2].recorded_at],
  ]);
  assert.equal(points.some(point => point.type === 'blood_pressure'), false);
});

test('flagged and malformed values remain inspectable and cannot enter unflagged numeric trends', () => {
  const rows = [fact('heart_rate', 999, { metadata: { quality_flags: ['out_of_range:heart_rate', 'future_flag'] } }),
    fact('heart_rate', 72), fact('heart_rate', null), fact('heart_rate', ''), fact('heart_rate', '72bad'),
    fact('heart_rate', 73, { metadata: { quality_flags: 'broken' } })];
  const points = domain.healthObservations(rows);
  assert.deepEqual(points.filter(domain.isTrendObservation).map(point => point.value), [72]);
  assert.equal(points[0].rawValue, 999);
  const html = renderToStaticMarkup(React.createElement(domain.QualityNotice, { observations: points }));
  for (const text of ['999', 'out_of_range:heart_rate', 'future_flag', '无法识别的质量标记', '未纳入趋势', '不代表临床诊断']) assert.ok(html.includes(text), text);
  const visualization = renderToStaticMarkup(React.createElement(domain.Visualization, { data: rows }));
  assert.ok(visualization.includes('999'));
  assert.ok(visualization.includes('质量标记'));
  assert.ok(visualization.includes('心率'));
});

test('laboratory result_value and BSON timestamps retain their own source meanings', () => {
  const row = { data_type: 'lab_result', data_content: { test_name: '血糖', result_value: '6.2', unit: 'mmol/L' }, recorded_at: '2026-11-15T01:02:03' };
  assert.equal(domain.healthObservations([row], 'lab_result')[0].value, 6.2);
  assert.equal(domain.healthDataTimestamp(row.recorded_at), Date.parse('2026-11-15T01:02:03Z'));
  assert.equal(domain.healthDataTimestamp('2026-11-15T09:02:03+08:00'), domain.healthDataTimestamp(row.recorded_at));
});

test('timeline projection preserves quality flags, provenance and independently measured pressure values', () => {
  const first = fact('blood_pressure_systolic', 180, { metadata: { quality_flags: ['out_of_range:blood_pressure_systolic'], device_data_id: 'raw-1' } });
  const second = fact('blood_pressure_diastolic', 80, { recorded_at: '2026-11-15T03:00:00Z' });
  const items = domain.convertHealthDataToTimelineItems([first, second]);
  assert.equal(items.length, 2);
  assert.equal(items[0].timestamp, first.recorded_at);
  assert.equal(items[1].timestamp, second.recorded_at);
  assert.equal(items[0].value, 180);
  assert.equal(items[1].value, 80);
  assert.match(items[0].title, /收缩压/);
  assert.match(items[0].description, /质量标记：out_of_range:blood_pressure_systolic/);
  assert.equal(items[0].metadata.device_data_id, 'raw-1');
  assert.deepEqual(items[0].metadata.quality_flags, first.metadata.quality_flags);
  assert.equal(items[0].metadata.alert_level, undefined);
});
