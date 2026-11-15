// Real Chromium, the actual page/hooks/transport, and an isolated synthetic API.
// Run with Playwright installed, or REHAB_PLAYWRIGHT_MODULE=/path/to/playwright.
// No application server or business database is used.
const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { spawnSync } = require('node:child_process');
const { build } = require('esbuild');

let chromium;
try { ({ chromium } = require(process.env.REHAB_PLAYWRIGHT_MODULE || 'playwright')); }
catch { /* Explicit optional browser dependency; report skipped, never fake acceptance. */ }
const chrome = process.env.CHROME_BIN || ['google-chrome', 'chromium', 'chromium-browser']
  .map(name => spawnSync('which', [name], { encoding: 'utf8' }).stdout.trim()).find(Boolean);

async function applicationBundle() {
  return (await build({
    stdin: { resolveDir: path.resolve(__dirname, '../src'), loader: 'tsx', contents: `
      import React from 'react';
      import { createRoot } from 'react-dom/client';
      import { configureStore } from '@reduxjs/toolkit';
      import { Provider } from 'react-redux';
      import { BrowserRouter, Link, Route, Routes } from 'react-router-dom';
      import HealthRecords from './pages/Doctor/HealthRecords';
      const role = new URLSearchParams(location.search).get('role');
      const store = configureStore({ reducer: { auth: (state = { user: { id: 'operator', role } }) => state } });
      localStorage.setItem('token', 'synthetic-provider-token');
      createRoot(document.getElementById('root')).render(<Provider store={store}>
        <BrowserRouter basename="/medical"><nav>
          <Link to="/record/patient-a">打开患者甲</Link> |
          <Link to="/record/patient-slow">打开延迟患者</Link> |
          <Link to="/record/patient-b">打开患者乙</Link>
        </nav><Routes><Route path="/record/:patientId" element={<HealthRecords />} /></Routes></BrowserRouter>
      </Provider>);
    ` },
    bundle: true, platform: 'browser', format: 'iife', write: false, logLevel: 'silent',
    // Match Vite's ESM dependency resolution instead of nesting icon CJS defaults.
    plugins: [{ name: 'mui-icon-esm', setup(build) {
      build.onResolve({ filter: /^@mui\/icons-material\/[^/]+$/ }, args => ({
        path: path.join(path.dirname(require.resolve('@mui/icons-material/package.json')),
          'esm', `${args.path.split('/').at(-1)}.js`),
      }));
    } }],
    define: { 'import.meta.env.VITE_API_URL': 'undefined', 'import.meta.env.VITE_API_PREFIX': '"/medical"',
      'process.env.NODE_ENV': '"development"' },
  })).outputFiles[0].text;
}

function record(patient) {
  return { id: patient, name: patient === 'patient-a' ? '合成患者甲' : patient === 'patient-b' ? '合成患者乙' : '迟到患者不得显示',
    age: 60, gender: '女', height: 160, weight: 60, bloodType: '未记录', allergies: [], emergencyContact: '未设置',
    medicalHistory: [], rehabHistory: [], medications: [], vitalSigns: [{ _id: `${patient}-fact`,
      data_type: 'vital_sign', data: { type: 'heart_rate', value: patient === 'patient-a' ? 131 : 77, unit: 'bpm' },
      recorded_at: '2026-11-15T01:02:03', source: 'device',
      metadata: { quality_flags: patient === 'patient-a' ? ['out_of_range:heart_rate'] : [],
        device_data_id: `${patient}-raw`, measurement_source: 'automated' } }] };
}

function syntheticServer(bundle) {
  const calls = [];
  let slowResponse, slowClosed = false;
  const json = (res, payload) => {
    if (res.destroyed) return;
    res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(payload));
  };
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://localhost');
    if (url.pathname === '/medical/api/auth/config') return json(res, { mode: 'legacy' });
    const match = url.pathname.match(/^\/medical\/api\/(doctors|health-managers)\/health-records\/([^/]+)$/);
    if (match) {
      calls.push({ provider: match[1], patient: match[2], authorization: req.headers.authorization });
      if (match[2] === 'patient-slow') {
        slowClosed = false;
        slowResponse = res;
        res.on('close', () => { slowClosed = true; });
        return;
      }
      return json(res, record(match[2]));
    }
    if (url.pathname === '/medical/harness.js') {
      res.writeHead(200, { 'Content-Type': 'application/javascript' }); return res.end(bundle);
    }
    if (url.pathname.endsWith('favicon.ico')) { res.writeHead(204); return res.end(); }
    if (url.pathname.startsWith('/medical/record/')) {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      return res.end('<!doctype html><meta charset="utf-8"><div id="root"></div><script src="/medical/harness.js"></script>');
    }
    res.writeHead(404); res.end();
  });
  return { server, calls, get slowClosed() { return slowClosed; }, releaseSlow() {
    if (slowResponse) json(slowResponse, record('patient-slow'));
  } };
}

test('doctor and health-manager records render facts and reject stale patient results in Chromium',
  { skip: !chromium || !chrome ? 'Playwright module and Chromium are required for real browser acceptance' : false,
    timeout: 45000 }, async t => {
    const app = syntheticServer(await applicationBundle());
    await new Promise(resolve => app.server.listen(0, '127.0.0.1', resolve));
    const origin = `http://127.0.0.1:${app.server.address().port}`;
    const browser = await chromium.launch({ executablePath: chrome, headless: true, args: ['--no-sandbox'] });
    t.after(async () => {
      app.releaseSlow(); await browser.close();
      app.server.closeAllConnections(); await new Promise(resolve => app.server.close(resolve));
    });
    for (const [role, provider] of [['doctor', 'doctors'], ['health_manager', 'health-managers']]) {
      await t.test(role, async () => {
        const context = await browser.newContext({ viewport: { width: 1360, height: 1000 } });
        const page = await context.newPage();
        page.setDefaultTimeout(8000);
        const exceptions = [];
        const consoleErrors = [];
        page.on('pageerror', error => { exceptions.push(error.message); t.diagnostic(error.message); });
        page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()); });
        const start = app.calls.length;
        await page.goto(`${origin}/medical/record/patient-a?role=${role}`);
        await page.getByText('合成患者甲', { exact: true }).waitFor().catch(async error => {
          t.diagnostic(JSON.stringify({ calls: app.calls.slice(start), body: await page.locator('body').innerText(), exceptions }));
          throw error;
        });
        await page.getByRole('tab', { name: '生命体征', exact: true }).click();
        await page.getByText('131 bpm', { exact: true }).waitFor();
        await page.getByText('数据质量标记：out_of_range:heart_rate', { exact: true }).waitFor();
        assert.deepEqual(app.calls.slice(start), [{ provider, patient: 'patient-a', authorization: 'Bearer synthetic-provider-token' }]);
        if (process.env.REHAB_BROWSER_ARTIFACT_DIR) {
          fs.mkdirSync(process.env.REHAB_BROWSER_ARTIFACT_DIR, { recursive: true });
          await page.screenshot({ path: path.join(process.env.REHAB_BROWSER_ARTIFACT_DIR, `provider-records-${role}-facts.png`), fullPage: true });
        }

        await page.getByRole('link', { name: '打开延迟患者' }).click();
        await page.waitForURL('**/record/patient-slow');
        await page.getByText('合成患者甲', { exact: true }).waitFor({ state: 'hidden' });
        await page.waitForFunction(() => document.querySelector('[role="progressbar"]') !== null);
        // Wait for the actual slow request before switching the same mounted page to B.
        const deadline = Date.now() + 5000;
        while (!app.calls.slice(start).some(call => call.patient === 'patient-slow') && Date.now() < deadline) {
          await new Promise(resolve => setTimeout(resolve, 10));
        }
        assert.ok(app.calls.slice(start).some(call => call.patient === 'patient-slow'));
        await page.evaluate(() => {
          window.latePatientSeen = false;
          new MutationObserver(() => {
            if (document.body.innerText.includes('迟到患者不得显示')) window.latePatientSeen = true;
          }).observe(document.body, { childList: true, subtree: true, characterData: true });
        });
        await page.getByRole('link', { name: '打开患者乙' }).click();
        await page.getByText('合成患者乙', { exact: true }).waitFor();
        await page.getByText('77 bpm', { exact: true }).waitFor();
        assert.ok(app.slowClosed, 'the previous HTTP request is cancelled before its server response is released');
        app.releaseSlow();
        await page.waitForTimeout(100);
        assert.equal(await page.evaluate(() => window.latePatientSeen), false);
        assert.equal(await page.getByText('合成患者甲', { exact: true }).count(), 0);
        assert.equal(await page.getByText('迟到患者不得显示', { exact: true }).count(), 0);
        assert.equal(await page.getByText('数据质量标记：out_of_range:heart_rate', { exact: true }).count(), 0);
        assert.deepEqual(app.calls.slice(start).map(call => [call.provider, call.patient]),
          [[provider, 'patient-a'], [provider, 'patient-slow'], [provider, 'patient-b']]);
        assert.deepEqual(exceptions, []);
        assert.deepEqual(consoleErrors, [], 'no browser errors or invalid DOM nesting warnings');
        if (process.env.REHAB_BROWSER_ARTIFACT_DIR) {
          fs.mkdirSync(process.env.REHAB_BROWSER_ARTIFACT_DIR, { recursive: true });
          await page.screenshot({ path: path.join(process.env.REHAB_BROWSER_ARTIFACT_DIR, `provider-records-${role}.png`), fullPage: true });
        }
        await context.close();
      });
    }
  });
