const assert = require('node:assert/strict');
const { createClient } = require('../miniprogram/services/api');
let call;
const storage = new Map();
const wx = {
  getStorageSync: key => storage.get(key), removeStorageSync: key => storage.delete(key),
  request(options) { call = options; options.success({ statusCode: 401, data: { detail: '已失效' } }); },
};
(async () => {
  const api = createClient('https://care.test/api', () => wx);
  api.setMiniToken('temporary'); api.setSession({ id: 'u1', role: 'patient' });
  const first = api.getSession().sessionId;
  api.clearSession(); api.setMiniToken('new'); api.setSession({ id: 'u1', role: 'patient' });
  assert.notEqual(api.getSession().sessionId, first, 'same user must receive a new session generation');
  await assert.rejects(api.request('/patients/todo-items'), /已失效/);
  assert.equal(call.header.Authorization, 'Bearer new');
  assert.equal(api.getSession(), null);
  assert.equal(api.getMiniToken(), '');
  let oldRequest;
  wx.request = options => { oldRequest = options; };
  api.setMiniToken('old'); api.setSession({ id: 'u1', role: 'patient' });
  const pending = api.request('/patients/todo-items');
  api.setMiniToken('fresh'); api.setSession({ id: 'u1', role: 'patient' });
  oldRequest.success({ statusCode: 401, data: { detail: '已失效' } });
  await assert.rejects(pending, /已失效/);
  assert.equal(api.getMiniToken(), 'fresh');
  assert.equal(api.getSession().user.id, 'u1');
  let uploadCall;
  wx.uploadFile = options => { uploadCall = options; options.success({ statusCode: 201, data: JSON.stringify({ id: 'a'.repeat(32) }) }); };
  const uploaded = await api.uploadFile('/rehabilitation/plans/0123456789abcdef01234567/patient-feedback/media', '/tmp/train.mp4');
  assert.equal(uploaded.id, 'a'.repeat(32));
  assert.equal(uploadCall.name, 'file');
  assert.equal(uploadCall.header.Authorization, 'Bearer fresh');
  let finishUpload;
  wx.uploadFile = options => { finishUpload = options; };
  const staleUpload = api.uploadFile('/rehabilitation/plans/0123456789abcdef01234567/patient-feedback/media', '/tmp/train.mp4');
  api.clearSession(); api.setMiniToken('next'); api.setSession({ id: 'u1', role: 'patient' });
  finishUpload.success({ statusCode: 201, data: '{"id":"old"}' });
  await assert.rejects(staleUpload, /登录状态已变化/);
  console.log('PASS: session generation and authentication failure clear');
})().catch(error => { console.error(error); process.exitCode = 1; });
