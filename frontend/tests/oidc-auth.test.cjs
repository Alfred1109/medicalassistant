const assert = require('node:assert/strict');
const { test } = require('node:test');
const Module = require('node:module');
const path = require('node:path');
const { buildSync } = require('esbuild');
const { configureStore } = require('@reduxjs/toolkit');
const axios = require('axios');
const compiled = buildSync({
  stdin: { contents: `export * from './services/authSession'; export * from './store/slices/authSlice'; export {default as reducer} from './store/slices/authSlice'; export {default as http} from './services/httpClient'; export {api as queryApi} from './store/api';`, resolveDir: path.resolve(__dirname, '../src'), loader: 'ts' },
  bundle: true, platform: 'node', format: 'cjs', write: false,
  external: ['axios', '@reduxjs/toolkit', '@reduxjs/toolkit/query/react'], define: { 'import.meta.env.VITE_API_URL': 'undefined', 'import.meta.env.VITE_API_PREFIX': '"/medical"' }, logLevel: 'silent',
}).outputFiles[0].text;
const user = { id: 'actor-1', role: 'doctor', name: 'Doctor', email: 'doctor@example.invalid', createdAt: '', updatedAt: '' };
function fixture({ mode = 'oidc', session = { authenticated: true, identity_state: 'bound', clinical_access: true, user }, configError = null, postError = null } = {}) {
  const entries = new Map([['token', 'old-bearer'], ['refresh_token', 'old-refresh'], ['persist:root', '{"auth":"stale"}']]);
  global.localStorage = { getItem: k => entries.get(k) ?? null, setItem: (k,v) => entries.set(k,String(v)), removeItem: k => entries.delete(k) };
  global.window = { location: { origin: 'https://rehab.example.invalid', protocol: 'https:', pathname: '/medical/auth/login', href: '' } };
  global.document = { cookie: '__Host-rehab_csrf=csrf-proof' };
  const calls = [];
  let proxy;
  proxy = new Proxy(axios, { get(target, name) {
    if (name === 'default') return proxy;
    if (name === 'get') return async (url, options) => {
      calls.push({ method: 'get', url, options });
      if (url.endsWith('/auth/config')) {
        if (configError) throw configError;
        return { data: { mode, login_url: 'https://rehab.example.invalid/medical/api/auth/oidc/start' } };
      }
      if (typeof session === 'function') return session(url, options);
      if (session instanceof Error) throw session;
      return { data: session };
    };
    if (name === 'put') return async (url, data, options) => { calls.push({ method: 'put', url, data, options }); return { data: user }; };
    if (name === 'post') return async (url, data, options) => {
      calls.push({ method: 'post', url, data, options });
      if (postError) throw postError;
      return { status: 204 };
    };
    return Reflect.get(target, name);
  } });
  const filename = path.resolve(__dirname, '.oidc-test.cjs');
  const loaded = new Module(filename, module); loaded.filename = filename; loaded.paths = Module._nodeModulePaths(__dirname);
  const inherited = loaded.require.bind(loaded); loaded.require = n => n === 'axios' ? proxy : inherited(n);
  loaded._compile(compiled, filename);
  const api = loaded.exports;
  const store = configureStore({ reducer: { auth: api.reducer, [api.queryApi.reducerPath]: api.queryApi.reducer }, middleware: getDefault => getDefault().concat(api.queryApi.middleware) });
  const httpCalls = [];
  api.http.defaults.adapter = async config => { httpCalls.push(config); return { data: {}, status: 200, statusText: 'OK', headers: {}, config }; };
  return { ...api, store, entries, calls, httpCalls };
}

test('OIDC bootstrap discards persisted bearer and accepts only a bound server session', async () => {
  const f = fixture();
  await f.store.dispatch(f.checkAuthStatus()).unwrap();
  assert.equal(f.store.getState().auth.mode, 'oidc');
  assert.equal(f.store.getState().auth.token, null);
  assert.deepEqual(f.store.getState().auth.user, user);
  assert.equal(f.entries.size, 0);
  assert.deepEqual(f.calls.map(c => c.url), ['/medical/api/auth/config', '/medical/api/auth/session']);
  assert.equal(f.calls.at(-1).options.withCredentials, true);
  assert.equal(f.calls.at(-1).options.headers, undefined);
});

test('pending binding and absent clinical access never create an authenticated business user', async () => {
  for (const session of [
    { authenticated: true, identity_state: 'pending_binding', clinical_access: false, user },
    { authenticated: true, identity_state: 'bound', clinical_access: false, user },
    { authenticated: false, user },
  ]) {
    const f = fixture({ session });
    await f.store.dispatch(f.checkAuthStatus()).unwrap();
    assert.equal(f.store.getState().auth.user, null);
    assert.equal(f.store.getState().auth.token, null);
  }
});

test('unavailable source and malformed bound identity fail closed', async () => {
  const unavailable = Object.assign(new Error('unavailable'), { response: { status: 503 } });
  const f = fixture({ session: unavailable });
  await assert.rejects(f.store.dispatch(f.checkAuthStatus()).unwrap(), /身份服务暂时不可用/);
  assert.equal(f.store.getState().auth.user, null);
  const malformed = fixture({ session: { authenticated: true, identity_state: 'bound', clinical_access: true, user: { id: '', role: 'admin' } } });
  await assert.rejects(malformed.store.dispatch(malformed.checkAuthStatus()).unwrap(), /有效的业务账号/);
  assert.equal(malformed.store.getState().auth.user, null);
});

test('OIDC shared transport sends Cookie and CSRF for writes, never stale Authorization', async () => {
  const f = fixture();
  await f.http.post('/patients', {}, { headers: { Authorization: 'Bearer supplied-old' } });
  assert.equal(f.httpCalls[0].withCredentials, true);
  assert.equal(f.httpCalls[0].headers.get('X-CSRF-Token'), 'csrf-proof');
  assert.equal(f.httpCalls[0].headers.get('Authorization'), undefined);
  f.entries.set('token', 'planted-bearer');
  await f.http.get('/patients');
  assert.equal(f.httpCalls[1].headers.get('Authorization'), undefined);
  assert.equal(f.httpCalls[1].headers.get('X-CSRF-Token'), undefined);
  document.cookie = '';
  await assert.rejects(f.http.delete('/patients/id'), /验证信息缺失/);
  assert.equal(f.httpCalls.length, 2);
});

test('configuration failure cannot send protected HTTP or fall back to legacy credentials', async () => {
  const f = fixture({ configError: new Error('offline') });
  await assert.rejects(f.http.get('/patients'), /offline/);
  assert.equal(f.httpCalls.length, 0);
  assert.equal(f.entries.get('token'), 'old-bearer');
});

test('OIDC logout posts CSRF and only clears local identity after server success', async () => {
  const f = fixture();
  await f.store.dispatch(f.checkAuthStatus()).unwrap();
  await f.store.dispatch(f.signOut()).unwrap();
  const call = f.calls.at(-1);
  assert.equal(call.url, '/medical/api/auth/logout');
  assert.equal(call.options.withCredentials, true);
  assert.equal(call.options.headers['X-CSRF-Token'], 'csrf-proof');
  assert.equal(f.store.getState().auth.user, null);
  const failed = fixture({ postError: new Error('offline') });
  await failed.store.dispatch(failed.checkAuthStatus()).unwrap();
  await assert.rejects(failed.store.dispatch(failed.signOut()).unwrap(), /退出失败/);
  assert.deepEqual(failed.store.getState().auth.user, user);
});

test('OIDC WebSocket uses same-origin Cookie and strips URL token while legacy retains it', async () => {
  const f = fixture();
  const url = await f.authenticatedWebSocketUrl('wss://rehab.example.invalid/medical/ws/notifications?token=stale&other=value');
  assert.equal(new URL(url).searchParams.has('token'), false);
  assert.equal(new URL(url).searchParams.get('other'), 'value');
  await assert.rejects(f.authenticatedWebSocketUrl('wss://other.example.invalid/ws'), /同源/);
  const legacy = fixture({ mode: 'legacy' });
  assert.equal(new URL(await legacy.authenticatedWebSocketUrl('wss://rehab.example.invalid/ws')).searchParams.get('token'), 'old-bearer');
});

test('OIDC credential thunks never call legacy login or registration', async () => {
  const f = fixture();
  await assert.rejects(f.store.dispatch(f.login({ email: 'a@example.invalid', password: 'never-send' })).unwrap(), /统一登录/);
  await assert.rejects(f.store.dispatch(f.register({ name: 'a', email: 'a@example.invalid', password: 'never-send' })).unwrap(), /统一登录/);
  assert.equal(f.calls.filter(c => c.method === 'post').length, 0);
});

test('logout invalidates a late cookie-session check', async () => {
  let resolve;
  const pending = new Promise(r => { resolve = r; });
  const f = fixture({ session: () => pending });
  const check = f.store.dispatch(f.checkAuthStatus());
  await new Promise(r => setImmediate(r));
  f.store.dispatch(f.logout());
  resolve({ data: { authenticated: true, identity_state: 'bound', clinical_access: true, user } });
  await check;
  assert.equal(f.store.getState().auth.user, null);
});


test('OIDC profile writes use current transport mode instead of a stale stored bearer', async () => {
  const f = fixture();
  await f.store.dispatch(f.updateUserProfile({ name: 'Doctor' })).unwrap();
  const call = f.calls.at(-1);
  assert.equal(call.method, 'put');
  assert.equal(call.options.withCredentials, true);
  assert.equal(call.options.headers['X-CSRF-Token'], 'csrf-proof');
  assert.equal(call.options.headers.Authorization, undefined);
});

test('RTK mutations enforce Cookie and CSRF consistently with the Axios adapters', async t => {
  const originalRequest = global.Request;
  const originalFetch = global.fetch;
  t.after(() => { global.Request = originalRequest; global.fetch = originalFetch; });
  global.Request = class extends originalRequest {
    constructor(input, init) { super(typeof input === 'string' && input.startsWith('/') ? 'https://rehab.example.invalid' + input : input, init); }
  };
  const requests = [];
  global.fetch = async request => { requests.push(request); return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } }); };
  const f = fixture();
  const result = await f.store.dispatch(f.queryApi.endpoints.createPatient.initiate({ name: 'patient' })).unwrap();
  assert.deepEqual(result, {});
  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, 'https://rehab.example.invalid/medical/api/patients');
  assert.equal(requests[0].credentials, 'include');
  assert.equal(requests[0].headers.get('X-CSRF-Token'), 'csrf-proof');
  assert.equal(requests[0].headers.get('Authorization'), null);
  f.store.dispatch(f.queryApi.util.resetApiState());
});


test('late profile response after logout cannot resurrect a cookie-authenticated user', async () => {
  const f = fixture();
  await f.store.dispatch(f.checkAuthStatus()).unwrap();
  const action = f.updateUserProfile.pending('profile-request', { name: 'Changed' });
  f.store.dispatch(action);
  f.store.dispatch(f.logout());
  f.store.dispatch(f.updateUserProfile.fulfilled(user, 'profile-request', { name: 'Changed' }));
  assert.equal(f.store.getState().auth.user, null);
  assert.equal(f.store.getState().auth.token, null);
});
