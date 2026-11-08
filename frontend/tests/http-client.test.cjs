const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');
const axios = require('axios');

function deferred() {
  let resolve, reject;
  const promise = new Promise((ok, fail) => { resolve = ok; reject = fail; });
  return { promise, resolve, reject };
}

function fixture(refresh = async () => ({ data: { access_token: 'new-token', refresh_token: 'new-refresh', expires_in: 3600 } })) {
  const values = new Map();
  const localStorage = { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) };
  const window = { location: { pathname: '/app/doctor/form-fill-tasks', href: '' } };
  const cache = new Map();
  const refreshCalls = [];
  const keys = { TOKEN: 'token', REFRESH_TOKEN: 'refresh_token', USER: 'user', TOKEN_EXPIRY: 'token_expiry' };
  function load(name) {
    if (cache.has(name)) return cache.get(name);
    const filename = path.resolve(__dirname, `../src/services/${name}.ts`);
    const compiled = ts.transpileModule(readFileSync(filename, 'utf8'), {
      compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, esModuleInterop: true },
    });
    const module = { exports: {} };
    vm.runInNewContext(compiled.outputText, {
      module, exports: module.exports, localStorage, window, console, Date,
      require(specifier) {
        if (specifier === 'axios') return { create: axios.create, post: async (...args) => { refreshCalls.push(args); return refresh(...args); } };
        if (specifier === '../config/constants') return { API_BASE_URL: '/deployment/api', STORAGE_KEYS: keys };
        if (specifier.startsWith('./')) return load(specifier.slice(2));
        throw new Error(`unexpected module ${specifier}`);
      },
    }, { filename });
    cache.set(name, module.exports);
    return module.exports;
  }
  const http = load('httpClient').default;
  const calls = [];
  http.defaults.adapter = async config => {
    calls.push(config);
    return { data: { ok: true, url: config.url }, status: 200, statusText: 'OK', headers: {}, config };
  };
  return { http, client: load('apiClient').default, api: load('api').default, calls, refreshCalls, values, window };
}

function session(f, token = 'old-token', refreshToken = 'old-refresh', expires = Date.now() + 1000) {
  f.values.set('token', token);
  f.values.set('refresh_token', refreshToken);
  f.values.set('token_expiry', String(expires));
  f.values.set('user', 'stored-user');
}
const unauthorized = config => new axios.AxiosError('unauthorized', 'ERR_BAD_REQUEST', config, null, { status: 401 });

test('response and data-only callers share transport while preserving timeout, headers and credentials', async () => {
  const f = fixture();
  f.values.set('token', 'current-token');
  assert.equal(f.api, f.http);
  const response = await f.api.get('/response');
  assert.equal(response.data.ok, true);
  assert.equal(response.status, 200);
  for (const [verb, invoke] of [
    ['get', () => f.client.get('/data')], ['post', () => f.client.post('/data', { x: 1 })],
    ['put', () => f.client.put('/data', { x: 2 })], ['delete', () => f.client.delete('/data')],
  ]) {
    const data = await invoke();
    assert.equal(data.ok, true);
    assert.equal('status' in data, false);
    assert.equal(f.calls.at(-1).method, verb);
    assert.equal(f.calls.at(-1).timeout, 15000);
  }
  await f.client.get('/custom', { timeout: 3210, withCredentials: true, headers: { 'X-Custom': 'kept' }, params: { page: 2 } });
  assert.equal(f.calls[0].timeout, 10000);
  assert.equal(f.calls[0].baseURL, '/deployment/api');
  assert.equal(f.calls[0].withCredentials, undefined);
  assert.equal(f.calls.at(-1).withCredentials, true);
  assert.equal(f.calls.at(-1).timeout, 3210);
  assert.equal(f.calls.at(-1).headers.get('X-Custom'), 'kept');
  assert.equal(f.calls.at(-1).headers.get('Authorization'), 'Bearer current-token');
  assert.equal(f.calls.at(-1).params.page, 2);
});

test('concurrent adapters refresh once and every protected request uses the new token', async () => {
  const gate = deferred();
  const f = fixture(async () => { await gate.promise; return { data: { access_token: 'new-token', refresh_token: 'new-refresh', expires_in: 3600 } }; });
  session(f);
  const requests = [f.api.get('/one'), f.client.get('/two')];
  await new Promise(done => setImmediate(done));
  assert.equal(f.refreshCalls.length, 1);
  assert.equal(f.calls.length, 0);
  gate.resolve();
  await Promise.all(requests);
  assert.equal(f.calls.length, 2);
  assert.ok(f.calls.every(call => call.headers.get('Authorization') === 'Bearer new-token'));
  assert.equal(f.values.get('token'), 'new-token');
  assert.equal(f.values.get('refresh_token'), 'new-refresh');
  assert.equal(f.refreshCalls[0][0], '/deployment/api/users/refresh-token');
  assert.equal(f.refreshCalls[0][1].refresh_token, 'old-refresh');
});

test('refresh failure rejects all pending requests without sending protected requests or looping', async () => {
  const gate = deferred();
  const failure = new Error('refresh unavailable');
  const f = fixture(() => gate.promise);
  session(f);
  const requests = Promise.allSettled([f.api.get('/one'), f.client.get('/two')]);
  await new Promise(done => setImmediate(done));
  gate.reject(failure);
  const results = await requests;
  assert.ok(results.every(result => result.status === 'rejected' && result.reason === failure));
  assert.equal(f.refreshCalls.length, 1);
  assert.equal(f.calls.length, 0);
  assert.equal(f.values.size, 0);
  assert.equal(f.window.location.href, '/login');
});

test('invalid refresh response cannot become an Authorization header', async () => {
  const f = fixture(async () => ({ data: { refresh_token: 'r', expires_in: 1 } }));
  session(f);
  await assert.rejects(f.client.get('/one'), /令牌刷新响应无效/);
  assert.equal(f.calls.length, 0);
  assert.equal(f.values.size, 0);
});

test('credential entry has no old bearer or recursive refresh; protected 401 clears current credentials', async () => {
  const f = fixture();
  session(f);
  await f.api.post('/users/login', { username: 'test' });
  await f.client.post('/users/register', { name: 'test' });
  await f.api.post('/users/refresh-token', { refresh_token: 'test' });
  assert.equal(f.refreshCalls.length, 0);
  assert.ok(f.calls.every(call => !call.headers.get('Authorization')));
  f.http.defaults.adapter = async config => { throw unauthorized(config); };
  session(f, 'current', 'refresh', Date.now() + 3600000);
  await assert.rejects(f.client.get('/protected'));
  assert.equal(f.values.size, 0);
  assert.equal(f.window.location.href, '/login');
  session(f, 'current', 'refresh', Date.now() + 3600000);
  f.window.location.href = '';
  await assert.rejects(f.api.post('/users/login', {}));
  assert.equal(f.window.location.href, '');
  assert.equal(f.values.get('token'), 'current');
});

test('logout during refresh cannot restore a session or send the pending request', async () => {
  const gate = deferred();
  const f = fixture(() => gate.promise);
  session(f);
  const pending = assert.rejects(f.client.get('/one'), /登录状态已变化/);
  await new Promise(done => setImmediate(done));
  f.values.clear();
  gate.resolve({ data: { access_token: 'stale', refresh_token: 'stale-refresh', expires_in: 3600 } });
  await pending;
  assert.equal(f.values.size, 0);
  assert.equal(f.calls.length, 0);
  assert.equal(f.window.location.href, '');
});

test('old refresh success or failure cannot overwrite or clear a replacement session', async () => {
  for (const success of [true, false]) {
    const gate = deferred();
    const f = fixture(() => gate.promise);
    session(f);
    const pending = assert.rejects(f.api.get('/old'));
    await new Promise(done => setImmediate(done));
    session(f, 'replacement', 'replacement-refresh', Date.now() + 3600000);
    if (success) gate.resolve({ data: { access_token: 'stale', refresh_token: 'stale-refresh', expires_in: 3600 } });
    else gate.reject(new Error('old refresh failed'));
    await pending;
    assert.equal(f.values.get('token'), 'replacement');
    assert.equal(f.values.get('refresh_token'), 'replacement-refresh');
    assert.equal(f.calls.length, 0);
    assert.equal(f.window.location.href, '');
  }
});

test('delayed old-session 401 cannot invalidate a newly logged-in account', async () => {
  const gate = deferred();
  const f = fixture();
  session(f, 'old', 'old-refresh', Date.now() + 3600000);
  f.http.defaults.adapter = async config => { await gate.promise; throw unauthorized(config); };
  const pending = assert.rejects(f.client.get('/old'));
  await new Promise(done => setImmediate(done));
  session(f, 'new', 'new-refresh', Date.now() + 3600000);
  gate.resolve();
  await pending;
  assert.equal(f.values.get('token'), 'new');
  assert.equal(f.values.get('refresh_token'), 'new-refresh');
  assert.equal(f.window.location.href, '');
});

test('network and non-authentication errors preserve caller error identity and current session', async () => {
  const f = fixture();
  f.values.set('token', 'current-token');
  const failure = new axios.AxiosError('forbidden', 'ERR_BAD_REQUEST', {}, null, { status: 403, data: { detail: 'denied' } });
  f.http.defaults.adapter = async () => { throw failure; };
  await assert.rejects(f.api.get('/one'), error => error === failure);
  await assert.rejects(f.client.get('/two'), error => error === failure);
  assert.equal(f.values.get('token'), 'current-token');
  assert.equal(f.window.location.href, '');
});
