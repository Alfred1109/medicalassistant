const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { base64Url, createPkcePair, miniProgramRandomBytes, sha256 } = require('../miniprogram/utils/miniAuth');

async function testPkce() {
  const rfcVerifier = 'dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk';
  assert.equal(base64Url(sha256(Buffer.from(rfcVerifier, 'ascii'))), 'E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM');
  const fixed = Uint8Array.from({ length: 32 }, (_, i) => i);
  const pair = await createPkcePair(async length => {
    assert.equal(length, 32);
    return fixed;
  });
  assert.equal(pair.verifier.length, 43);
  assert.equal(pair.challenge.length, 43);
  assert.match(pair.verifier, /^[A-Za-z0-9_-]{43}$/);
  assert.match(pair.challenge, /^[A-Za-z0-9_-]{43}$/);
  assert.equal(pair.challenge, '6oZqdX5MOLq_qBJ8vppAnT4fk6AP8UiP9zX8-Rev_9A');
  await assert.rejects(createPkcePair(async () => new Uint8Array(31)), /invalid length/);

  const previousWx = global.wx;
  global.wx = { getRandomValues({ length, success }) { success({ randomValues: fixed.slice(0, length).buffer }); } };
  assert.equal(new Uint8Array(await miniProgramRandomBytes(32)).length, 32);
  global.wx = {};
  await assert.rejects(miniProgramRandomBytes(32), /不支持安全随机数/);
  global.wx = previousWx;
}

async function testMiniLoginFlow() {
  const calls = [];
  const storage = new Map();
  const pollStatuses = ['oidc_started', 'awaiting_confirmation', 'ready'];
  const routes = {
    '/auth/config': { mode: 'oidc' },
    '/auth/mini/transactions': { transaction_id: 'txn_test_1', webview_url: 'https://system.test/oneid/mini/txn_test_1', expires_in: 300, poll_interval: 2 },
    '/auth/mini/transactions/txn_test_1/exchange': { access_token: 'opaque-mini-secret', token_type: 'Bearer', expires_in: 120, user: { id: 'actor-7', display_name: '测试账号', role: 'patient' } },
    '/users/me': { id: 'actor-7', name: '测试账号', role: 'patient' },
    '/devices/': [],
    '/auth/mini/session/logout': {},
  };
  const wx = {
    getRandomValues({ length, success }) { success({ randomValues: Uint8Array.from({ length }, (_, i) => i).buffer }); },
    getStorageSync(key) { return storage.get(key); },
    setStorageSync(key, value) { storage.set(key, value); },
    removeStorageSync(key) { storage.delete(key); },
    request(options) {
      const pathName = new URL(options.url).pathname.replace('/api', '');
      calls.push({ path: pathName, method: options.method, data: options.data, header: options.header });
      const data = pathName.endsWith('/poll')
        ? { status: pollStatuses.shift(), expires_in: 290, ...(pollStatuses.length === 0 ? { user: { id: 'actor-7', display_name: '测试账号', role: 'patient' } } : {}) }
        : routes[pathName];
      if (data === undefined) return options.fail({ errMsg: `unmocked route: ${pathName}` });
      options.success({ statusCode: 200, data });
    },
  };
  global.wx = wx;
  const apiConfig = { apiBaseUrl: 'https://system.test/api' };
  const source = fs.readFileSync(path.join(__dirname, '../miniprogram/pages/index/index.js'), 'utf8');
  let page;
  const context = {
    wx,
    Page(definition) { page = definition; },
    setTimeout() { return 1; },
    clearTimeout() {},
    Date,
    Promise,
    Number,
    String,
    Array,
    Math,
    require(request) {
      if (request === '../../config') return apiConfig;
      if (request === '../../services/api') return require('../miniprogram/services/api').createClient(apiConfig.apiBaseUrl, () => wx);
      if (request === '../../libs/veepoo/index') return { veepooBle: {}, veepooFeature: {} };
      if (request === '../../utils/readings') return require('../miniprogram/utils/readings');
      if (request === '../../utils/miniAuth') return require('../miniprogram/utils/miniAuth');
      throw new Error(`unexpected module: ${request}`);
    },
  };
  vm.runInNewContext(source, context, { filename: 'index.js' });
  page.data = { ...page.data };
  page.setData = updates => Object.assign(page.data, updates);
  await page.initializeAuthMode();
  await page.startOneIdLogin();
  assert.equal(page.data.oidcWebviewUrl, routes['/auth/mini/transactions'].webview_url);
  assert.equal(page._oidcTransaction.verifier.length, 43);
  await page.pollOneIdTransaction();
  assert.equal(page.data.oidcReadyUser, null, 'oidc_started remains in progress');
  await page.pollOneIdTransaction();
  assert.equal(page.data.oidcReadyUser, null, 'awaiting_confirmation remains in progress');
  await page.pollOneIdTransaction();
  const verifier = page._oidcTransaction.verifier;
  assert.equal(page.data.oidcReadyUser.display_name, '测试账号');
  assert.equal(page.data.oidcReadyRoleLabel, '患者');
  assert.equal(page.data.loggedIn, false, 'ready alone must not log the user in');
  await page.confirmOneIdActor();
  assert.equal(page.data.loggedIn, true);
  assert.equal(page.data.identityConfirmed, false, 'exchange alone must not expose patient operations');
  assert.equal(page.data.patients.length, 0);
  await page.confirmOneIdIdentity();
  assert.equal(page.data.identityConfirmed, true);
  assert.equal(page.data.patients.length, 1);
  assert.equal(storage.has('rehab_access_token'), false, 'mini credential must not be persisted');
  const start = calls.find(call => call.path === '/auth/mini/transactions');
  assert.equal(start.method, 'POST');
  assert.equal(start.data.code_challenge.length, 43);
  assert.equal(calls.some(call => call.path.includes(verifier)), false, 'verifier must never enter a URL');
  const exchange = calls.find(call => call.path.endsWith('/exchange'));
  assert.equal(exchange.method, 'POST');
  assert.equal(exchange.data.verifier.length, 43);
  assert.equal(exchange.header.Authorization, undefined);
  assert(calls.some(call => call.path === '/users/me' && call.header.Authorization === 'Bearer opaque-mini-secret'));
  assert.equal(calls.some(call => call.path.includes('password') || call.path.endsWith('/users/login')), false);
  await page.logout();
  const logout = calls.find(call => call.path === '/auth/mini/session/logout');
  assert.equal(logout.method, 'POST');
  assert.equal(logout.header.Authorization, 'Bearer opaque-mini-secret');
  assert(calls.filter(call => call.path.startsWith('/auth/mini/transactions/')).every(call => !call.header.Authorization),
    'transaction calls must not receive the mini session bearer');
  delete global.wx;
}

(async () => {
  await testPkce();
  await testMiniLoginFlow();
  console.log('PASS: PKCE secure-random handling and mocked OneID transaction, consent gates, in-memory mini credential');
})().catch(error => { console.error(error); process.exitCode = 1; });
