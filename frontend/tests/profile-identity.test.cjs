// Run from frontend/: node --test tests/profile-identity.test.cjs
const assert = require('node:assert/strict');
const { test } = require('node:test');
const Module = require('node:module');
const path = require('node:path');
const { buildSync } = require('esbuild');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const { Provider } = require('react-redux');
const { configureStore } = require('@reduxjs/toolkit');

const filename = path.resolve(__dirname, '.profile-identity.compiled.cjs');
const compiled = buildSync({
  entryPoints: [path.resolve(__dirname, '../src/pages/Profile/Profile.tsx')],
  bundle: true, platform: 'node', format: 'cjs', write: false,
  packages: 'external', logLevel: 'silent',
  define: { 'import.meta.env.VITE_API_URL': 'undefined', 'import.meta.env.VITE_API_PREFIX': 'undefined' },
}).outputFiles[0].text;
const loaded = new Module(filename, module);
loaded.filename = filename;
loaded.paths = Module._nodeModulePaths(__dirname);
global.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
loaded._compile(compiled, filename);
const Profile = loaded.exports.default;

function render(user) {
  const store = configureStore({ reducer: () => ({ auth: { user } }) });
  return renderToStaticMarkup(React.createElement(Provider, { store }, React.createElement(Profile)));
}
function user(role) {
  return { id: role, name: '真实账号-' + role, email: role + '@example.invalid', role,
    createdAt: '2026-01-02T00:00:00Z', updatedAt: '' };
}

test('each role sees its actual logged-in identity without fabricated profile fields', () => {
  for (const role of ['patient', 'doctor', 'health_manager', 'admin']) {
    const html = render(user(role));
    assert.ok(html.includes('真实账号-' + role));
    assert.ok(html.includes(role + '@example.invalid'));
    assert.ok(html.includes('未提供'));
    assert.ok(html.includes('姓名、电话、简介和头像保存在本系统'));
    assert.ok(html.includes('统一登录账号的密码在问卷系统里修改'));
    for (const text of ['张三', 'zhangsan@example.com', '138****1234', '10年康复医学经验']) {
      assert.equal(html.includes(text), false, text);
    }
    for (const operation of ['编辑资料', '修改头像', '修改密码']) assert.ok(html.includes(operation));
    assert.equal(html.includes('type="password"'), false);
    assert.ok(html.includes('type="file"'));
    assert.equal(html.includes('密码已成功更新'), false);
    assert.equal(html.includes('个人资料已更新'), false);
  }
});

test('missing session displays no stale or synthetic account', () => {
  const html = render(null);
  assert.ok(html.includes('当前没有已验证的账号资料'));
  assert.equal(html.includes('@example'), false);
  assert.equal(html.includes('编辑资料'), false);
});

test('nullable profile fields stay unknown', () => {
  const html = render({ ...user('patient'), name: '', createdAt: 'invalid', phone: null, department: null, bio: null });
  assert.ok(html.includes('未提供'));
  assert.equal(html.includes('Invalid Date'), false);
  assert.equal(html.includes('[object Object]'), false);
});

test('local accounts explain the local password boundary', () => {
  const html = render({ ...user('doctor'), local_password: true });
  assert.ok(html.includes('这个账号有本地密码，可以在这里修改'));
  assert.equal(html.includes('本地密码已更新'), false);
});
