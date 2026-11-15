const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const Module = require('node:module');
const path = require('node:path');
const { transformSync } = require('esbuild');
const filename = path.resolve(__dirname, '../src/utils/healthTimeline.ts');
const compiled = transformSync(readFileSync(filename, 'utf8'), { loader: 'ts', format: 'cjs' }).code;
const loaded = new Module(filename, module);
loaded._compile(compiled, filename);
const { timelineMeasurement } = loaded.exports;

test('timeline retains laboratory names, results and units including zero', () => {
  assert.equal(timelineMeasurement({ test_name: '肌酐', result_value: 88, unit: 'µmol/L' }), '肌酐：88 µmol/L');
  assert.equal(timelineMeasurement({ type: 'heart_rate', value: 0, unit: 'bpm' }), 'heart_rate：0 bpm');
});

test('timeline renders all composite blood-pressure components without flattening or pairing facts', () => {
  assert.equal(timelineMeasurement({ type: 'blood_pressure', value: { systolic: 120, diastolic: 80 }, unit: 'mmHg' }),
    'blood_pressure：{"systolic":120,"diastolic":80} mmHg');
});

test('missing measurement leaves historical description available instead of inventing a value', () => {
  assert.equal(timelineMeasurement(), null);
  assert.equal(timelineMeasurement({ value: null }), null);
});
