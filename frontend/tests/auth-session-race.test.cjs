// Run from frontend/: node --test tests/auth-session-race.test.cjs
// Compile the actual TypeScript slice; only HTTP and browser storage are fixtures.
const assert = require('node:assert/strict');
const { test } = require('node:test');
const Module = require('node:module');
const path = require('node:path');
const { buildSync } = require('esbuild');
const { configureStore } = require('@reduxjs/toolkit');
const axios = require('axios');

const source = path.resolve(__dirname, '../src/store/slices/authSlice.ts');
const compiled = new Map();

function compile(apiRoot, prefix) {
  const key = JSON.stringify([apiRoot, prefix]);
  if (!compiled.has(key)) {
    compiled.set(key, buildSync({
      entryPoints: [source],
      bundle: true,
      platform: 'node',
      format: 'cjs',
      write: false,
      external: ['axios', '@reduxjs/toolkit'],
      define: {
        'import.meta.env.VITE_API_URL': apiRoot === undefined ? 'undefined' : JSON.stringify(apiRoot),
        'import.meta.env.VITE_API_PREFIX': prefix === undefined ? 'undefined' : JSON.stringify(prefix),
      },
      logLevel: 'silent',
    }).outputFiles[0].text);
  }
  return compiled.get(key);
}

function fixture(token = 'token-A', apiRoot, prefix) {
  const entries = new Map(token ? [['token', token]] : []);
  global.localStorage = {
    getItem: key => entries.get(key) ?? null,
    setItem: (key, value) => entries.set(key, String(value)),
    removeItem: key => entries.delete(key),
  };
  const filename = path.resolve(__dirname, '.auth-session-race.compiled.cjs');
  const loaded = new Module(filename, module);
  loaded.filename = filename;
  loaded.paths = Module._nodeModulePaths(__dirname);
  loaded._compile(compile(apiRoot, prefix), filename);
  const actions = loaded.exports;
  const store = configureStore({ reducer: { auth: actions.default } });
  return { store, actions, entries };
}

function user(id, role = 'patient') {
  return { id, role, name: id, email: `${id}@example.invalid`, createdAt: '', updatedAt: '' };
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function replaceSession(f, token, nextUser) {
  f.entries.set('token', token);
  f.entries.set('userRole', nextUser.role);
  f.store.dispatch(f.actions.login.fulfilled(
    { token, user: nextUser }, 'fixture-login',
    { email: nextUser.email, password: 'fixture-only' },
  ));
}

test('session checks cannot mutate a replacement or logged-out session', async t => {
  const originalGet = axios.get;
  const originalStorage = global.localStorage;
  t.after(() => { axios.get = originalGet; global.localStorage = originalStorage; });

  for (const outcome of ['fulfilled', 'rejected']) {
    await t.test(`late A ${outcome} preserves completed B and its token`, async () => {
      const f = fixture();
      const a = deferred();
      const b = deferred();
      axios.get = (_url, config) => config.headers.Authorization === 'Bearer token-A' ? a.promise : b.promise;
      const checkA = f.store.dispatch(f.actions.checkAuthStatus());
      const userB = user('user-B', 'doctor');
      replaceSession(f, 'token-B', userB);
      const checkB = f.store.dispatch(f.actions.checkAuthStatus());
      b.resolve({ data: userB });
      await checkB;
      if (outcome === 'fulfilled') a.resolve({ data: user('user-A', 'admin') });
      else a.reject({ response: { data: { detail: 'old A expired' } } });
      await checkA;
      assert.equal(f.store.getState().auth.token, 'token-B');
      assert.deepEqual(f.store.getState().auth.user, userB);
      assert.equal(f.store.getState().auth.error, null);
      assert.equal(f.entries.get('token'), 'token-B');
      assert.equal(f.entries.get('userRole'), 'doctor');
    });
  }

  await t.test('late A failure cannot cancel an in-flight B check', async () => {
    const f = fixture();
    const a = deferred();
    const b = deferred();
    axios.get = (_url, config) => config.headers.Authorization === 'Bearer token-A' ? a.promise : b.promise;
    const checkA = f.store.dispatch(f.actions.checkAuthStatus());
    replaceSession(f, 'token-B', user('user-B'));
    const checkB = f.store.dispatch(f.actions.checkAuthStatus());
    const requestB = f.store.getState().auth.sessionCheckRequestId;
    a.reject(new Error('late A'));
    await checkA;
    assert.equal(f.store.getState().auth.checking, true);
    assert.equal(f.store.getState().auth.sessionCheckRequestId, requestB);
    assert.equal(f.entries.get('token'), 'token-B');
    b.resolve({ data: user('verified-B') });
    await checkB;
    assert.equal(f.store.getState().auth.user.id, 'verified-B');
  });

  for (const outcome of ['fulfilled', 'rejected']) {
    await t.test(`logout ignores a late ${outcome} validation`, async () => {
      const f = fixture();
      const pending = deferred();
      axios.get = () => pending.promise;
      const check = f.store.dispatch(f.actions.checkAuthStatus());
      f.store.dispatch(f.actions.logout());
      if (outcome === 'fulfilled') pending.resolve({ data: user('old-admin', 'admin') });
      else pending.reject(new Error('late error'));
      await check;
      assert.equal(f.store.getState().auth.token, null);
      assert.equal(f.store.getState().auth.user, null);
      assert.equal(f.store.getState().auth.checking, false);
      assert.equal(f.store.getState().auth.error, null);
      assert.equal(f.entries.has('token'), false);
    });
  }

  await t.test('request identity protects concurrent checks of the same token', async () => {
    const f = fixture();
    const first = deferred();
    const second = deferred();
    let calls = 0;
    axios.get = () => (++calls === 1 ? first.promise : second.promise);
    const check1 = f.store.dispatch(f.actions.checkAuthStatus());
    const check2 = f.store.dispatch(f.actions.checkAuthStatus());
    second.resolve({ data: user('latest') });
    await check2;
    first.reject(new Error('older request failed'));
    await check1;
    assert.equal(f.store.getState().auth.user.id, 'latest');
    assert.equal(f.store.getState().auth.token, 'token-A');
    assert.equal(f.entries.get('token'), 'token-A');
  });

  await t.test('current expiry clears its own session and stored role', async () => {
    const f = fixture();
    f.entries.set('userRole', 'admin');
    axios.get = async () => { throw { response: { data: { detail: 'expired' } } }; };
    await f.store.dispatch(f.actions.checkAuthStatus());
    assert.equal(f.store.getState().auth.token, null);
    assert.equal(f.store.getState().auth.user, null);
    assert.equal(f.store.getState().auth.error, 'expired');
    assert.equal(f.entries.has('token'), false);
    assert.equal(f.entries.has('userRole'), false);
  });

  await t.test('expiry in this tab does not erase a newer stored token', async () => {
    const f = fixture();
    const pending = deferred();
    axios.get = () => pending.promise;
    const check = f.store.dispatch(f.actions.checkAuthStatus());
    f.entries.set('token', 'other-tab-token-B');
    f.entries.set('userRole', 'doctor');
    pending.reject(new Error('old tab expired'));
    await check;
    assert.equal(f.store.getState().auth.token, null);
    assert.equal(f.entries.get('token'), 'other-tab-token-B');
    assert.equal(f.entries.get('userRole'), 'doctor');
  });

  await t.test('registration result invalidates validation of the old session', async () => {
    const f = fixture();
    const pending = deferred();
    axios.get = () => pending.promise;
    const check = f.store.dispatch(f.actions.checkAuthStatus());
    const registered = user('registered-patient');
    f.entries.set('token', 'registered-token');
    f.store.dispatch(f.actions.register.fulfilled(
      { token: 'registered-token', user: registered }, 'fixture-register',
      { name: registered.name, email: registered.email, password: 'fixture-only' },
    ));
    pending.resolve({ data: user('previous-user', 'admin') });
    await check;
    assert.equal(f.store.getState().auth.token, 'registered-token');
    assert.deepEqual(f.store.getState().auth.user, registered);
    assert.equal(f.entries.get('token'), 'registered-token');
  });
});

test('all identity requests share the configured API root', async t => {
  const originalGet = axios.get;
  const originalPost = axios.post;
  const originalPut = axios.put;
  const originalStorage = global.localStorage;
  t.mock.timers.enable({ apis: ['setTimeout'] });
  t.after(() => {
    axios.get = originalGet;
    axios.post = originalPost;
    axios.put = originalPut;
    global.localStorage = originalStorage;
    t.mock.timers.reset();
  });

  for (const [configured, expected, prefix] of [
    [undefined, '/api'],
    [undefined, '/medical/api', '/medical'],
    ['/rehab/api/', '/rehab/api'],
    ['https://forms.example.invalid/site', 'https://forms.example.invalid/site/api'],
  ]) {
    await t.test(`identity requests use ${expected}`, async () => {
      const f = fixture(null, configured, prefix);
      const calls = [];
      const nextUser = user('api-root-patient');
      axios.post = async url => {
        calls.push(url);
        return {
          status: 200,
          data: url.endsWith('/register')
            ? { user: nextUser, token: 'registered-token' }
            : { user: nextUser, access_token: 'login-token' },
        };
      };
      axios.get = async url => { calls.push(url); return { data: nextUser }; };
      axios.put = async url => { calls.push(url); return { data: nextUser }; };
      await f.store.dispatch(f.actions.register({
        name: nextUser.name, email: nextUser.email, password: 'fixture-only',
      })).unwrap();
      await f.store.dispatch(f.actions.login({ email: nextUser.email, password: 'fixture-only' })).unwrap();
      await f.store.dispatch(f.actions.checkAuthStatus()).unwrap();
      await f.store.dispatch(f.actions.updateUserProfile({ name: nextUser.name })).unwrap();
      assert.deepEqual(calls, ['register', 'login', 'me', 'profile'].map(endpoint => `${expected}/users/${endpoint}`));
      assert.equal(f.store.getState().auth.token, 'login-token');
      assert.deepEqual(f.store.getState().auth.user, nextUser);
    });
  }
});
