const assert = require('node:assert/strict');
const { createServer } = require('node:http');
const { test } = require('node:test');
const { buildSync } = require('esbuild');
const Module = require('node:module');
const path = require('node:path');
const { configureStore } = require('@reduxjs/toolkit');
const axios = require('axios');

// Real transports and actual service/thunk consumers; a server reproduces
// FastAPI's slash redirect that previously escaped the deployment prefix.
test('all slash-collection consumers stay under the configured prefix without redirects', async t => {
  const received = [];
  const server = createServer((req, res) => {
    received.push({ method: req.method, path: req.url });
    res.setHeader('Content-Type', 'application/json');
    if (req.url === '/medical/api/auth/config') return res.end(JSON.stringify({ mode: 'legacy' }));
    if (/^\/medical\/api\/(agents|notifications|devices)(?:\?|$)/.test(req.url)) {
      res.statusCode = 307;
      res.setHeader('Location', req.url.replace('/medical', '').replace(/(\?|$)/, '/$1'));
      return res.end('{}');
    }
    if (!/^\/medical\/api\/(agents|notifications|devices)\/(?:\?|$)/.test(req.url)) res.statusCode = 404;
    res.end('[]');
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise(resolve => server.close(resolve)));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const oldStorage = global.localStorage, oldWindow = global.window, oldProxy = axios.defaults.proxy;
  t.after(() => { global.localStorage = oldStorage; global.window = oldWindow; axios.defaults.proxy = oldProxy; });
  global.localStorage = { getItem: () => null, setItem() {}, removeItem() {} };
  global.window = { location: { origin, protocol: 'http:', pathname: '/medical/app/dashboard' } };
  axios.defaults.proxy = false;
  const source = `export {apiService} from './services/api'; export {notificationApi} from './services/notificationService'; export {default as dashboardService} from './services/dashboardService'; export {fetchAgents,createAgent} from './store/slices/agentSlice';`;
  const code = buildSync({ stdin: { contents: source, resolveDir: path.resolve(__dirname, '../src'), loader: 'ts' }, bundle: true, write: false, format: 'cjs', platform: 'node', external: ['axios', '@reduxjs/toolkit'],
    define: { 'import.meta.env.VITE_API_URL': JSON.stringify(origin + '/medical/api'), 'import.meta.env.VITE_API_PREFIX': '"/medical"' }, logLevel: 'silent' }).outputFiles[0].text;
  const filename = path.resolve(__dirname, '.prefixed-collections.cjs');
  const loaded = new Module(filename, module); loaded.filename = filename; loaded.paths = Module._nodeModulePaths(__dirname); loaded._compile(code, filename);
  const api = loaded.exports;
  const store = configureStore({ reducer: { auth: () => ({ token: null }) } });
  await api.apiService.agent.getAgents();
  await api.apiService.agent.createAgent({ name: 'fixture' });
  await store.dispatch(api.fetchAgents()).unwrap();
  await store.dispatch(api.createAgent({ name: 'fixture' })).unwrap();
  await api.notificationApi.getNotifications({ limit: 5 });
  await api.dashboardService.getNotifications(5);
  await api.apiService.getUserDevices();
  assert.equal(received.length, 8, 'one config + seven requests, no extra redirect request');
  assert.equal(received.filter(r => r.path === '/medical/api/auth/config').length, 1);
  assert.equal(received.filter(r => r.path.startsWith('/medical/api/agents/')).length, 4);
  assert.equal(received.filter(r => r.path.startsWith('/medical/api/notifications/')).length, 2);
  assert.equal(received.filter(r => r.path === '/medical/api/devices/').length, 1);
  assert.ok(received.every(r => r.path.startsWith('/medical/api/')));
});
