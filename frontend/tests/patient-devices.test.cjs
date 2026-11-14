const assert = require('node:assert/strict');
const { test } = require('node:test');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const { transformSync } = require('esbuild');

function load(relative, replacements) {
  const file = path.resolve(__dirname, '../src', relative);
  const compiled = new Module(file, module);
  compiled.filename = file;
  compiled.paths = Module._nodeModulePaths(__dirname);
  compiled.require = name => name in replacements ? replacements[name] : require(name);
  compiled._compile(transformSync(readFileSync(file, 'utf8'), { loader: 'ts', format: 'cjs' }).code, file);
  return compiled.exports;
}

test('patient device queries carry an explicit patient filter without changing the legacy account adapter', async () => {
  const calls = [];
  const transport = { get: async (...args) => { calls.push(args); return { data: [] }; } };
  const { apiService } = load('services/api.ts', { './httpClient': transport,
    '../config/apiPaths': { API_COLLECTION_PATHS: { DEVICES: '/devices/' } } });
  await apiService.getPatientDevices('patient-a');
  await apiService.getUserDevices('legacy-account-parameter');
  assert.deepEqual(calls, [['/devices/', { params: { patient_id: 'patient-a' } }], ['/devices/']]);
});

test('the device adapter rejects another patient response and binds to the selected patient', async () => {
  const calls = [];
  let rows = [{ id: 'device-a', patient_id: 'patient-a' }];
  const apiService = {
    getPatientDevices: async id => { calls.push(['list', id]); return { data: rows }; },
    bindUserDevice: async (account, payload) => { calls.push(['bind', account, payload]); return { data: payload }; },
  };
  const { deviceService } = load('services/deviceService.ts', { './api': { apiService } });
  await assert.rejects(deviceService.getPatientDevices(''), /先选择患者/);
  assert.equal(calls.length, 0);
  assert.deepEqual(await deviceService.getPatientDevices('patient-a'), rows);
  rows = [{ id: 'foreign-device', patient_id: 'patient-b' }];
  await assert.rejects(deviceService.getPatientDevices('patient-a'), /所属患者/);
  rows = null;
  await assert.rejects(deviceService.getPatientDevices('patient-a'), /所属患者/);
  await deviceService.bindDevice({ patient_id: 'patient-a', device_type: '血压计', name: '合成设备' });
  assert.deepEqual(calls.at(-1), ['bind', '', { patient_id: 'patient-a', device_type: '血压计', name: '合成设备' }]);
});
