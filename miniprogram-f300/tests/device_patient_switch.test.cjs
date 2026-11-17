const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const apiFactory = require('../miniprogram/services/api').createClient;

async function run() {
  let connectionCallback;
  let disconnects = 0;
  const wx = {
    getStorageSync() { return ''; }, removeStorageSync() {},
    request(o) { o.success({ statusCode: 200, data: [] }); },
  };
  const api = apiFactory('https://test.invalid/api', () => wx);
  api.setMiniToken('mock');
  api.setSession({ id: 'staff', role: 'doctor' });
  const ble = {
    veepooWeiXinSDKStopSearchBleManager(cb) { cb(); },
    veepooWeiXinSDKloseBluetoothAdapterManager(cb) { disconnects += 1; cb(); },
    veepooWeiXinSDKBleConnectionServicesCharacteristicsNotifyManager(_d, cb) { connectionCallback = cb; },
  };
  let page;
  const context = {
    wx, Page(definition) { page = definition; }, Date, Promise, Number, String, Array, Math,
    setTimeout() { return 1; }, clearTimeout() {},
    require(name) {
      if (name === '../../config') return { apiBaseUrl: 'https://test.invalid/api' };
      if (name === '../../services/api') return api;
      if (name === '../../libs/veepoo/index') return { veepooBle: ble, veepooFeature: {} };
      if (name === '../../utils/readings') return require('../miniprogram/utils/readings');
      if (name === '../../utils/miniAuth') return require('../miniprogram/utils/miniAuth');
      throw new Error(name);
    },
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../miniprogram/pages/index/index.js'), 'utf8'), context);
  page.data = { ...page.data, loggedIn: true, identityConfirmed: true,
    user: { id: 'staff', role: 'doctor' }, patients: [{ id: 'p1' }, { id: 'p2' }], patientIndex: 0,
    scanResults: [{ deviceId: 'watch1' }], connected: true, authenticated: true,
    hardwareId: 'watch1', selectedDeviceId: 'record1', pendingReading: { value: 77 }, confirmUpload: true };
  page.setData = values => Object.assign(page.data, values);
  page.connect({ currentTarget: { dataset: { deviceid: 'watch1' } } });
  assert.equal(typeof connectionCallback, 'function');
  await page.onPatientChange({ detail: { value: '1' } });
  connectionCallback({ connection: true });
  assert.equal(page.data.patientIndex, 1);
  assert.equal(page.data.authenticated, false);
  assert.equal(page.data.connected, false);
  assert.equal(page.data.hardwareId, '');
  assert.equal(page.data.pendingReading, null);
  assert.equal(page.data.confirmUpload, false);
  assert.equal(page.data.selectedDeviceId, '');
  assert.ok(disconnects >= 1);
  console.log('PASS: patient switch clears readings and rejects stale BLE connection callback');
}
run().catch(error => { console.error(error); process.exitCode = 1; });
