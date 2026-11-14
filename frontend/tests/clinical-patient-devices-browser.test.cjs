// 医护患者设备管理页（frontend/src/pages/Clinical/PatientDevices.tsx）的真实浏览器验收。
// 形态沿用项目既有约定：
// - node --test + assert/strict（同 tests/*.test.cjs）；
// - 真实 Chromium + 实际前端构建产物（dist）+ 合成 API + 隔离临时环境，
//   与 docs/embed-credential-contract-gap.md 记录的「浏览器测试使用实际前端和合成 API、
//   临时自签名 TLS」同一模式；本场景全部同源（静态资源与合成 API 同一 127.0.0.1 端口），
//   不涉及跨站 Cookie，因此无需 TLS。
// - Chromium 未安装或未构建 dist 时按既有模式跳过，不伪造结果。
// 浏览器经 CDP（remote-debugging-port + WebSocket）驱动真实输入事件：
// 鼠标点击、文本输入，不通过 evaluate 直接调用 React 处理器。
// 运行：npm run build && node --test tests/clinical-patient-devices-browser.test.cjs

const assert = require('node:assert/strict');
const { test } = require('node:test');
const { spawn } = require('node:child_process');
const { execSync } = require('node:child_process');
const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');

const DIST_DIR = path.resolve(__dirname, '../dist');
const DEPLOY_PREFIX = '/medical';

// ---------------------------------------------------------------------------
// 真实浏览器（Chromium）启动与 CDP 会话
// ---------------------------------------------------------------------------

function findBrowserBinary() {
  for (const bin of ['google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser']) {
    try {
      const resolved = execSync(`command -v ${bin}`, { encoding: 'utf8' }).trim();
      if (resolved) return resolved;
    } catch { /* 该二进制不存在，尝试下一个 */ }
  }
  return null;
}

class CdpSession {
  constructor(wsUrl) {
    this.ws = new WebSocket(wsUrl);
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = new Map();
  }

  async connect() {
    await new Promise((resolve, reject) => {
      this.ws.addEventListener('open', () => resolve(), { once: true });
      this.ws.addEventListener('error', event => reject(new Error(`WebSocket 连接失败: ${event.message}`)), { once: true });
    });
    this.ws.addEventListener('message', event => {
      Promise.resolve(
        typeof event.data === 'string' ? event.data : event.data?.text?.(),
      ).then(raw => {
        if (!raw) return;
        let message;
        try { message = JSON.parse(raw); } catch { return; }
        if (message.id !== undefined) {
          const entry = this.pending.get(message.id);
          if (!entry) return;
          this.pending.delete(message.id);
          if (message.error) entry.reject(new Error(`CDP ${entry.method} 失败: ${message.error.message}`));
          else entry.resolve(message.result);
        } else if (message.method) {
          for (const handler of this.listeners.get(message.method) || []) {
            try { handler(message.params); } catch { /* 监听器自身错误不中断会话 */ }
          }
        }
      }).catch(() => {});
    });
  }

  send(method, params = {}) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject, method });
      this.ws.send(JSON.stringify({ id, method, params }));
      setTimeout(() => {
        if (this.pending.delete(id)) reject(new Error(`CDP ${method} 超时`));
      }, 20000);
    });
  }

  on(method, handler) {
    if (!this.listeners.has(method)) this.listeners.set(method, []);
    this.listeners.get(method).push(handler);
  }

  close() { try { this.ws.close(); } catch { /* 已关闭 */ } }
}

async function startBrowser() {
  const binary = findBrowserBinary();
  if (!binary) return null;
  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'rehab-devices-browser-'));

  // 先占用一个端口再释放，得到可用端口号（存在理论竞态，验收环境可接受）。
  const portHolder = http.createServer();
  const port = await new Promise(resolve => {
    portHolder.listen(0, '127.0.0.1', () => resolve(portHolder.address().port));
  });
  await new Promise(resolve => portHolder.close(resolve));

  const proc = spawn(binary, [
    '--headless',
    '--no-sandbox',
    '--disable-gpu',
    '--disable-dev-shm-usage',
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${userDataDir}`,
    '--window-size=1440,1000',
    '--no-first-run',
    '--no-default-browser-check',
    'about:blank',
  ], { stdio: 'ignore' });

  // 等待 DevTools 端口就绪。
  let ready = false;
  for (let i = 0; i < 100 && !ready; i += 1) {
    await new Promise(resolve => setTimeout(resolve, 100));
    try {
      const response = await fetch(`http://127.0.0.1:${port}/json/version`);
      ready = response.ok;
    } catch { /* 未就绪，继续等待 */ }
  }
  if (!ready) {
    proc.kill('SIGKILL');
    fs.rmSync(userDataDir, { recursive: true, force: true });
    throw new Error('浏览器 DevTools 端口未在 10 秒内就绪');
  }

  const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  const pageTarget = targets.find(target => target.type === 'page');
  if (!pageTarget?.webSocketDebuggerUrl) throw new Error('未找到浏览器页面目标');

  const session = new CdpSession(pageTarget.webSocketDebuggerUrl);
  await session.connect();
  await session.send('Page.enable');
  await session.send('Runtime.enable');
  await session.send('Network.enable');

  const consoleExceptions = [];
  const staticResourceFailures = [];
  session.on('Runtime.exceptionThrown', params => {
    const details = params.exceptionDetails || {};
    consoleExceptions.push(details.exception?.description || `${details.text} ${details.url || ''}`.trim());
  });
  session.on('Network.responseReceived', params => {
    const { response } = params;
    const url = response.url || '';
    // 合成 API 的错误状态是场景刻意注入的，只统计非 API 资源的失败（404 静态资源等）。
    if (!url.includes(`${DEPLOY_PREFIX}/api/`) && response.status >= 400) {
      staticResourceFailures.push(`${response.status} ${url}`);
    }
  });

  return {
    proc,
    session,
    consoleExceptions,
    staticResourceFailures,
    async close() {
      session.close();
      proc.kill('SIGKILL');
      await new Promise(resolve => { proc.once('exit', resolve); setTimeout(resolve, 3000); });
      fs.rmSync(userDataDir, { recursive: true, force: true });
    },
  };
}

// ---------------------------------------------------------------------------
// 页面操作辅助（全部经由真实输入事件或只读 evaluate）
// ---------------------------------------------------------------------------

async function evaluate(browser, expression, { awaitPromise = false } = {}) {
  const result = await browser.session.send('Runtime.evaluate', {
    expression,
    returnByValue: true,
    awaitPromise,
    userGesture: true,
  });
  if (result.exceptionDetails) {
    const detail = result.exceptionDetails;
    throw new Error(`页面 evaluate 出错: ${detail.exception?.description || detail.text}`);
  }
  return result.result?.value;
}

async function waitForExpr(browser, expression, label, timeout = 8000) {
  const ok = await evaluate(browser, `
    (async () => {
      const deadline = Date.now() + ${timeout};
      while (Date.now() < deadline) {
        try { if (${expression}) return true; } catch { /* 渲染中途可能短暂抛错 */ }
        await new Promise(resolve => setTimeout(resolve, 100));
      }
      return false;
    })()`, { awaitPromise: true });
  if (!ok) throw new Error(`等待超时: ${label}`);
}

const waitForText = (browser, text, timeout = 8000) =>
  waitForExpr(browser, `document.body.innerText.includes(${JSON.stringify(text)})`, `文本「${text}」`, timeout);

const pause = ms => new Promise(resolve => setTimeout(resolve, ms));

const bodyText = browser => evaluate(browser, 'document.body.innerText');

// 计算元素中心点，并确认该点的真实命中（document.elementFromPoint）就是目标元素
// 或其子元素。MUI 子菜单/对话框有展开动画，动画未完成时命中测试不通过——
// 这与真实用户的点击落空是同一回事，因此用它来决定「现在能不能点」。
function buildFinder(selector, { contains = null, exact = null } = {}) {
  if (contains === null && exact === null) return `document.querySelector(${JSON.stringify(selector)})`;
  return `[...document.querySelectorAll(${JSON.stringify(selector)})].find(el => ${
    exact !== null
      ? `el.textContent.trim() === ${JSON.stringify(exact)}`
      : `el.textContent.includes(${JSON.stringify(contains)})`
  })`;
}

async function resolveClickablePoint(browser, finder) {
  return evaluate(browser, `(() => {
    const el = (${finder});
    if (!el) return null;
    el.scrollIntoView({ block: 'center' });
    const rect = el.getBoundingClientRect();
    const x = rect.left + rect.width / 2;
    const y = rect.top + rect.height / 2;
    const hit = document.elementFromPoint(x, y);
    if (!hit || (hit !== el && !el.contains(hit))) return null; // 尚不可点击（动画/遮挡中）
    return { x, y };
  })()`);
}

async function dispatchClick(browser, point) {
  const { session } = browser;
  await session.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: point.x, y: point.y });
  await session.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: point.x, y: point.y, button: 'left', clickCount: 1 });
  await session.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: point.x, y: point.y, button: 'left', clickCount: 1 });
}

// 真实鼠标点击：等待元素可被命中（最多 attempts 次），再经 CDP 派发原生鼠标事件。
async function clickElement(browser, selector, options = {}, attempts = 30) {
  const finder = buildFinder(selector, options);
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const point = await resolveClickablePoint(browser, finder);
    if (point) {
      await dispatchClick(browser, point);
      return;
    }
    await pause(100);
  }
  throw new Error(`找不到可点击元素或元素不可点击: ${selector} contains=${options.contains} exact=${options.exact}`);
}

async function openSelect(browser, selector) {
  await clickElement(browser, selector);
  await waitForExpr(browser, `!!document.querySelector('ul[role="listbox"]')`, '下拉列表展开');
}

async function readSelectOptions(browser) {
  return evaluate(browser,
    `[...document.querySelectorAll('li[role="option"]')].map(li => li.textContent.trim())`);
}

async function chooseSelectOption(browser, selector, optionText) {
  await openSelect(browser, selector);
  await clickElement(browser, 'li[role="option"]', { exact: optionText });
  await waitForExpr(browser,
    `!document.querySelector('ul[role="listbox"]')`, '下拉列表收起');
}

// 通过 label 找到受控输入框，真实点击后经 Input.insertText 输入，并回读校验。
async function fillField(browser, labelText, value) {
  const finder = `[...document.querySelectorAll('label')].find(l => l.textContent.replace(/[*\\s]/g, '').trim() === ${JSON.stringify(labelText)})?.control`;
  let clicked = false;
  for (let attempt = 0; attempt < 30 && !clicked; attempt += 1) {
    const point = await resolveClickablePoint(browser, finder);
    if (point) {
      await dispatchClick(browser, point);
      clicked = true;
    } else {
      await pause(100);
    }
  }
  if (!clicked) throw new Error(`找不到输入框: ${labelText}`);
  await browser.session.send('Input.insertText', { text: value });
  const actual = await evaluate(browser, `(${finder})?.value ?? null`);
  assert.equal(actual, value, `输入框「${labelText}」内容不符`);
}

const buttonDisabled = (browser, text) => evaluate(browser,
  `[...document.querySelectorAll('button')].find(b => b.textContent.trim().includes(${JSON.stringify(text)}))?.disabled ?? null`);

const snackbarText = browser => evaluate(browser,
  `document.querySelector('.MuiSnackbarContent-message')?.innerText || ''`);

async function waitForSnackbar(browser, expected, timeout = 5000) {
  await waitForExpr(browser,
    `document.querySelector('.MuiSnackbarContent-message')?.innerText?.includes(${JSON.stringify(expected)})`,
    `通知消息「${expected}」`, timeout);
}

async function navigate(browser, url) {
  await browser.session.send('Page.navigate', { url });
  await waitForExpr(browser, `document.readyState === 'complete'`, '页面加载完成');
}

// ---------------------------------------------------------------------------
// 合成 API + 实际前端构建产物的同源隔离服务
// ---------------------------------------------------------------------------

const ISO_NOW = new Date().toISOString();

function freshState() {
  return {
    role: 'doctor',
    patients: [{ id: 'p1', name: '患者一' }, { id: 'p2', name: '患者二' }],
    devices: [
      { id: 'dev-1', device_type: '血压计', name: '合成血压计', patient_id: 'p1', status: 'active', model: 'BM-100', manufacturer: '合成医疗', connection_type: 'bluetooth', firmware_version: 'v1.0', battery_level: 76, last_connected: ISO_NOW },
      { id: 'dev-2', device_type: '手环', name: '合成手环', patient_id: 'p2', status: 'online', model: 'BAND-2', battery_level: 61, last_connected: ISO_NOW },
    ],
    // 患者角色的自有设备（GET /devices 不带 patient_id 的患者自选语义）。
    selfDevices: [
      { id: 'dev-self', device_type: '手环', name: '患者自有手环', patient_id: 'patient-1', status: 'online', model: 'BAND-SELF', battery_level: 90, last_connected: ISO_NOW },
    ],
    // 各场景按需注入的失败响应；null 表示正常路径。
    deviceListFailure: null,
    bindFailure: null,
    unbindFailure: null,
    readingFailure: null,
    deviceCounter: 100,
    calls: [],
    unknownApiPaths: [],
  };
}

function createSyntheticApp() {
  const state = freshState();
  const failuresSeen = [];

  const apiFailure = (failure) => {
    if (!failure) return null;
    failuresSeen.push(failure.status);
    return failure;
  };

  const respond = (res, status, payload) => {
    const body = JSON.stringify(payload ?? {});
    res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(body);
  };

  const readBody = req => new Promise(resolve => {
    const chunks = [];
    req.on('data', chunk => chunks.push(chunk));
    req.on('end', () => {
      try { resolve(JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}')); }
      catch { resolve({}); }
    });
  });

  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url, 'http://127.0.0.1');

    // 合成 API。
    if (url.pathname.startsWith(`${DEPLOY_PREFIX}/api/`)) {
      const method = req.method;
      const body = ['POST', 'PUT', 'DELETE'].includes(method) ? await readBody(req) : null;
      const apiPath = url.pathname.slice(DEPLOY_PREFIX.length); // 例如 /api/devices/
      state.calls.push({ method, path: apiPath, query: Object.fromEntries(url.searchParams), body });

      if (apiPath === '/api/auth/config') return respond(res, 200, { mode: 'legacy', login_url: null });

      if (apiPath === '/api/users/me') {
        const users = {
          doctor: { id: 'doctor-1', name: '陈医生', role: 'doctor', email: 'doctor@synthetic.local' },
          patient: { id: 'patient-1', name: '患者本人', role: 'patient', email: 'patient@synthetic.local' },
          health_manager: { id: 'hm-1', name: '健康管理师', role: 'health_manager', email: 'hm@synthetic.local' },
        };
        return respond(res, 200, users[state.role] || users.doctor);
      }

      if (apiPath === '/api/doctors/patients' || apiPath === '/api/health-managers/patients') {
        return respond(res, 200, state.patients);
      }

      if (apiPath === '/api/devices/' && method === 'GET') {
        const failure = apiFailure(state.deviceListFailure);
        if (failure) return respond(res, failure.status, failure.body);
        const patientId = url.searchParams.get('patient_id');
        if (patientId) {
          return respond(res, 200, state.devices.filter(device => device.patient_id === patientId));
        }
        // 患者自选语义：当前账号本人的设备。
        return respond(res, 200, state.selfDevices);
      }

      if (apiPath === '/api/devices/bind' && method === 'POST') {
        const failure = apiFailure(state.bindFailure);
        if (failure) return respond(res, failure.status, failure.body);
        const target = body.patient_id ? state.devices : state.selfDevices;
        state.deviceCounter += 1;
        const created = {
          id: `dev-new-${state.deviceCounter}`,
          device_type: body.device_type,
          name: body.name,
          patient_id: body.patient_id || 'patient-1',
          status: 'active',
          model: body.model || null,
          manufacturer: body.manufacturer || null,
          created_at: new Date().toISOString(),
        };
        target.push(created);
        return respond(res, 200, created);
      }

      const unbindMatch = apiPath.match(/^\/api\/devices\/([^/]+)\/unbind$/);
      if (unbindMatch && method === 'DELETE') {
        const failure = apiFailure(state.unbindFailure);
        if (failure) return respond(res, failure.status, failure.body);
        for (const list of [state.devices, state.selfDevices]) {
          const index = list.findIndex(device => device.id === unbindMatch[1]);
          if (index >= 0) list.splice(index, 1);
        }
        return respond(res, 200, { success: true });
      }

      const readingMatch = apiPath.match(/^\/api\/devices\/([^/]+)\/readings$/);
      if (readingMatch && method === 'POST') {
        const failure = apiFailure(state.readingFailure);
        if (failure) return respond(res, failure.status, failure.body);
        return respond(res, 200, { id: `reading-${Date.now()}`, device_id: readingMatch[1], ...body });
      }

      if (/^\/api\/devices\/[^/]+\/status$/.test(apiPath)) {
        return respond(res, 200, { status: 'online', battery_level: 82, signal_strength: 4, last_sync_time: ISO_NOW, message: '合成状态正常' });
      }

      if (/^\/api\/devices\/[^/]+\/data$/.test(apiPath)) return respond(res, 200, []);

      if (/^\/api\/devices\/[^/]+\/sync$/.test(apiPath) && method === 'POST') {
        return respond(res, 200, { success: true, message: '合成同步完成' });
      }

      if (/^\/api\/devices\/[^/]+\/config$/.test(apiPath) && method === 'PUT') {
        return respond(res, 200, { success: true, message: '合成配置已保存' });
      }

      if (/^\/api\/devices\/[^/]+\/repair$/.test(apiPath) && method === 'POST') {
        return respond(res, 200, { success: true, message: '合成修复完成', repair_actions: [], repair_results: [] });
      }

      // 应用启动期其他页面的次要请求：如实记录，返回空对象，不参与断言。
      state.unknownApiPaths.push(`${method} ${url.pathname}`);
      return respond(res, 200, {});
    }

    // 实际前端构建产物（dist），带部署前缀，SPA 路由回退到 index.html。
    let relativePath = url.pathname.slice(DEPLOY_PREFIX.length) || '/';
    if (relativePath === '/') relativePath = '/index.html';
    let filePath = path.join(DIST_DIR, relativePath);
    if (!path.resolve(filePath).startsWith(path.resolve(DIST_DIR))) return respond(res, 403, {});
    if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
      filePath = path.join(DIST_DIR, 'index.html');
    }
    if (!fs.existsSync(filePath)) return respond(res, 404, {});
    const extensions = {
      '.html': 'text/html; charset=utf-8',
      '.js': 'text/javascript',
      '.css': 'text/css',
      '.svg': 'image/svg+xml',
      '.map': 'application/json',
      '.json': 'application/json',
      '.png': 'image/png',
    };
    const ext = path.extname(filePath);
    res.writeHead(200, { 'Content-Type': extensions[ext] || 'application/octet-stream' });
    fs.createReadStream(filePath).pipe(res);
    return undefined;
  });

  const port = new Promise(resolve => {
    server.listen(0, '127.0.0.1', () => resolve(server.address().port));
  });

  return {
    state,
    failuresSeen,
    server,
    port,
    close: () => new Promise(resolve => server.close(resolve)),
  };
}

// ---------------------------------------------------------------------------
// 验收场景
// ---------------------------------------------------------------------------

test('医护患者设备管理页真实浏览器验收（Chromium + 实际前端 + 合成 API）', async t => {
  const browserBinary = findBrowserBinary();
  if (!fs.existsSync(path.join(DIST_DIR, 'index.html'))) {
    return t.skip('缺少前端构建产物 dist/，请先运行 npm run build 再执行浏览器验收');
  }
  if (!browserBinary) {
    return t.skip('未安装 Chromium/Chrome，跳过浏览器渲染层');
  }

  const app = createSyntheticApp();
  const port = await app.port;
  const base = `http://127.0.0.1:${port}`;
  const browser = await startBrowser();
  try {
    assert.ok(browser, '浏览器应成功启动');
    const { state } = app;

    const seedSession = async role => {
      await navigate(browser, `${base}${DEPLOY_PREFIX}/login`);
      await evaluate(browser, `localStorage.clear(); localStorage.setItem('token', 'synthetic-acceptance-token');`);
      state.role = role;
    };

    // ---------------------------------------------------------------------
    // 场景 1：医护登录 → 菜单进入设备管理页 → 选择器只显示已授权患者 → 列表加载
    // ---------------------------------------------------------------------
    await t.test('场景1：医生经菜单进入设备管理页并加载已授权患者设备', async () => {
      await seedSession('doctor');
      await navigate(browser, `${base}${DEPLOY_PREFIX}/app/doctor`);
      await waitForText(browser, '患者管理');

      // 经侧边菜单进入：医生工作站 → 患者设备（菜单项是 ListItemButton，不是 button 元素）
      await clickElement(browser, '.MuiListItemButton-root', { contains: '医生工作站' });
      await waitForText(browser, '患者设备');
      await clickElement(browser, '.MuiListItemButton-root', { contains: '患者设备' });
      await waitForText(browser, '患者设备管理');
      assert.ok(
        await evaluate(browser, `window.location.pathname.endsWith('/app/doctor/devices')`),
        '菜单点击后应停在医生设备管理路由');

      // 选择器只显示合成 API 返回的已授权患者（患者名单加载完成后选择器才渲染）
      await waitForExpr(browser, `!!document.querySelector('.MuiSelect-select')`, '患者选择器出现');
      await chooseSelectOption(browser, '.MuiSelect-select', '患者一');
      await waitForText(browser, '合成血压计');
      const text = await bodyText(browser);
      assert.ok(text.includes('类型: 血压计'), '设备列表应展示设备类型');
      assert.ok(!text.includes('未授权患者'), '不应出现未授权患者');

      // 再次打开选择器核对候选名单
      await openSelect(browser, '.MuiSelect-select');
      const options = await readSelectOptions(browser);
      await clickElement(browser, 'li[role="option"]', { exact: '患者一' });
      assert.deepEqual(options, ['选择患者', '患者一', '患者二'],
        '患者选择器应只包含合成 API 返回的已授权患者');
      await waitForExpr(browser, `!document.querySelector('ul[role="listbox"]')`, '下拉列表收起');
      await waitForText(browser, '合成血压计');
    });

    // ---------------------------------------------------------------------
    // 场景 2：绑定设备——表单校验、成功刷新、403/409/503 失败可见且不破坏页面
    // ---------------------------------------------------------------------
    await t.test('场景2：绑定设备的校验、成功与失败路径', async () => {
      // 成功路径
      await clickElement(browser, 'button', { contains: '添加设备' });
      await waitForText(browser, '绑定新设备');
      assert.equal(await buttonDisabled(browser, '确认绑定'), true,
        '设备类型与名称为空时「确认绑定」应禁用');

      await chooseSelectOption(browser, '.MuiDialog-root .MuiSelect-select', '血压计');
      await fillField(browser, '设备名称', '合成血糖仪');
      await fillField(browser, '设备型号（选填）', 'GM-300');
      assert.equal(await buttonDisabled(browser, '确认绑定'), false, '必填项齐全后「确认绑定」应可用');
      await clickElement(browser, 'button', { contains: '确认绑定' });

      await waitForSnackbar(browser, '绑定成功');
      await waitForText(browser, '合成血糖仪');
      const bindCalls = state.calls.filter(call => call.path === '/api/devices/bind' && call.method === 'POST');
      assert.deepEqual(bindCalls.at(-1).body, {
        device_type: '血压计', name: '合成血糖仪', patient_id: 'p1', model: 'GM-300',
      }, '绑定请求应携带患者 ID 与设备字段');
      // 对话框退场动画结束后才卸载，等待而非立刻断言。
      await waitForExpr(browser,
        `![...document.querySelectorAll('h6')].some(el => el.textContent.includes('绑定新设备'))`,
        '成功后绑定对话框关闭');

      // 失败路径：403 / 409 / 503，错误可见且页面不崩、列表不脏
      const failureCases = [
        { status: 403, body: { detail: '没有该患者的设备操作权限' } },
        { status: 409, body: { detail: '设备名称已被该患者绑定' } },
        { status: 503, body: { error: 'PATIENT_IDENTITY_AMBIGUOUS', detail: '患者身份歧义' } },
      ];
      for (const failure of failureCases) {
        state.bindFailure = failure;
        await clickElement(browser, 'button', { contains: '添加设备' });
        await waitForText(browser, '绑定新设备');
        await chooseSelectOption(browser, '.MuiDialog-root .MuiSelect-select', '手环');
        await fillField(browser, '设备名称', '不应登记的设备');
        await clickElement(browser, 'button', { contains: '确认绑定' });

        const expectedMessage = failure.status === 503
          ? '绑定失败: 患者档案标识存在歧义，请联系管理员核查历史数据。'
          : `绑定失败: ${failure.body.detail}`;
        await waitForSnackbar(browser, expectedMessage);
        assert.ok(await bodyText(browser).then(text => text.includes('已绑定设备')),
          '失败后页面应保持可用');
        assert.ok(!(await bodyText(browser)).includes('不应登记的设备'),
          '失败提交不应进入设备列表');
        // 关闭对话框，进入下一个失败用例
        await clickElement(browser, 'button', { exact: '取消' });
      }
      state.bindFailure = null;
    });

    // ---------------------------------------------------------------------
    // 场景 3：解绑——确认交互、取消、成功后列表更新
    // ---------------------------------------------------------------------
    await t.test('场景3：解绑设备的确认交互与列表更新', async () => {
      // 注意：主标签页「设备管理」也是 button 元素且包含「管理」子串，必须精确匹配。
      await clickElement(browser, 'button', { exact: '管理' });
      await waitForText(browser, '基本信息');
      await clickElement(browser, 'button', { contains: '解除绑定' });
      await waitForText(browser, '确认解除绑定？');

      // 先取消：设备仍在列表
      await clickElement(browser, 'button', { exact: '取消' });
      await waitForExpr(browser, `!document.body.innerText.includes('确认解除绑定？')`, '确认对话框关闭');
      assert.ok((await bodyText(browser)).includes('合成血压计'), '取消解绑后设备仍在列表');

      // 确认解绑：列表更新（场景 2 绑定的「合成血糖仪」应保留）
      await clickElement(browser, 'button', { contains: '解除绑定' });
      await waitForText(browser, '确认解除绑定？');
      await clickElement(browser, 'button', { contains: '确认解绑' });
      await waitForSnackbar(browser, '已解绑');
      await waitForText(browser, '合成血糖仪');
      // 只检查设备列表条目：解绑 snackbar 文本本身包含设备名，不能以整页文本判断。
      await waitForExpr(browser,
        `![...document.querySelectorAll('.MuiListItem-root')].some(li => li.textContent.includes('合成血压计'))`,
        '解绑后设备应从列表消失');
      assert.ok(state.calls.some(call => call.method === 'DELETE' && /\/api\/devices\/dev-1\/unbind$/.test(call.path)),
        '应调用真实解绑端点');
    });

    // ---------------------------------------------------------------------
    // 场景 4：手工读数录入——成功与失败路径
    // ---------------------------------------------------------------------
    await t.test('场景4：手工读数录入的成功与失败路径', async () => {
      // 使用场景 2 绑定、场景 3 解绑后仍保留的「合成血糖仪」
      await clickElement(browser, 'button', { exact: '管理' });
      await waitForText(browser, '基本信息');
      await clickElement(browser, '.MuiTab-root', { contains: '数据同步' });
      await waitForText(browser, '登记读数');

      assert.equal(await buttonDisabled(browser, '登记读数'), true, '类型/数值为空时「登记读数」应禁用');
      await fillField(browser, '类型', '血压');
      await fillField(browser, '数值', '120/80');
      await fillField(browser, '单位', 'mmHg');
      await clickElement(browser, 'button', { contains: '登记读数' });
      await waitForSnackbar(browser, '已保存手工登记的读数');
      const readingCalls = state.calls.filter(call => call.path.endsWith('/readings') && call.method === 'POST');
      assert.equal(readingCalls.length, 1, '应恰好提交一次读数');
      assert.deepEqual(
        { data_type: readingCalls[0].body.data_type, value: readingCalls[0].body.value, unit: readingCalls[0].body.unit },
        { data_type: '血压', value: '120/80', unit: 'mmHg' },
        '读数载荷应与表单一致');

      // 失败路径：合成 API 返回 503，页面给出明确错误
      state.readingFailure = { status: 503, body: { error: 'PATIENT_IDENTITY_AMBIGUOUS', detail: '读数身份歧义' } };
      await fillField(browser, '数值', '130/85');
      await clickElement(browser, 'button', { contains: '登记读数' });
      await waitForSnackbar(browser, '患者档案标识存在歧义，请联系管理员核查历史数据。');
      assert.ok((await bodyText(browser)).includes('登记读数'), '失败后对话框应保持可用');
      state.readingFailure = null;
      await clickElement(browser, 'button', { contains: '关闭' });
    });

    // ---------------------------------------------------------------------
    // 场景 5：503 PATIENT_IDENTITY_AMBIGUOUS 的设备列表加载提示与恢复
    // ---------------------------------------------------------------------
    await t.test('场景5：503 PATIENT_IDENTITY_AMBIGUOUS 提示与重试恢复', async () => {
      state.deviceListFailure = { status: 503, body: { error: 'PATIENT_IDENTITY_AMBIGUOUS', message: 'ambiguous' } };
      // 切换患者触发 DeviceBinding 重新挂载并加载失败。
      // 只认 Alert 提示（场景 4 的失败 snackbar 也含同样文案，不能以整页文本判断）。
      await chooseSelectOption(browser, '.MuiSelect-select', '患者二');
      await waitForExpr(browser,
        `[...document.querySelectorAll('.MuiAlert-message')].some(el => el.textContent.includes('患者档案标识存在歧义'))`,
        '设备列表加载失败的明确提示');

      // 重试按钮恢复：清除失败后点击「重试」
      state.deviceListFailure = null;
      await clickElement(browser, 'button', { contains: '重试' });
      await waitForText(browser, '合成手环');
      await waitForExpr(browser,
        `![...document.querySelectorAll('.MuiAlert-message')].some(el => el.textContent.includes('患者档案标识存在歧义'))`,
        '恢复后错误提示消失');
    });

    // ---------------------------------------------------------------------
    // 场景 1 补充：健康管理师同一页面入口
    // ---------------------------------------------------------------------
    await t.test('场景1b：健康管理师经菜单进入同一设备管理页', async () => {
      await seedSession('health_manager');
      await navigate(browser, `${base}${DEPLOY_PREFIX}/app/health-manager`);
      await waitForText(browser, '患者管理');
      await clickElement(browser, '.MuiListItemButton-root', { contains: '健康管理师' });
      await waitForText(browser, '患者设备');
      await clickElement(browser, '.MuiListItemButton-root', { contains: '患者设备' });
      await waitForText(browser, '患者设备管理');
      await waitForExpr(browser, `!!document.querySelector('.MuiSelect-select')`, '患者选择器出现');
      await chooseSelectOption(browser, '.MuiSelect-select', '患者一');
      // 前面场景解绑了初始设备，此时患者一列表中是场景 2 绑定的合成血糖仪。
      await waitForText(browser, '合成血糖仪');
    });

    // ---------------------------------------------------------------------
    // 场景 6：患者角色入口回归——患者自己的设备绑定页仍可用
    // ---------------------------------------------------------------------
    await t.test('场景6：患者角色设备绑定页回归', async () => {
      await seedSession('patient');
      await navigate(browser, `${base}${DEPLOY_PREFIX}/app/patient/devices`);
      await waitForText(browser, '设备绑定与管理');
      await waitForText(browser, '患者自有手环');

      // 患者绑定走自选语义：请求不携带 patient_id
      await clickElement(browser, 'button', { contains: '添加设备' });
      await waitForText(browser, '绑定新设备');
      await chooseSelectOption(browser, '.MuiSelect-select', '血压计');
      await fillField(browser, '设备名称', '患者自选血压计');
      await clickElement(browser, 'button', { contains: '确认绑定' });
      await waitForSnackbar(browser, '绑定成功');
      await waitForText(browser, '患者自选血压计');
      const bindCalls = state.calls.filter(call => call.path === '/api/devices/bind' && call.method === 'POST');
      assert.equal(bindCalls.at(-1).body.patient_id, undefined,
        '患者自选绑定不应携带 patient_id');
      assert.ok(state.calls.some(call => call.path === '/api/devices/' && call.method === 'GET' && !call.query.patient_id),
        '患者列表应走无 patient_id 的自选端点语义');
    });

    // ---------------------------------------------------------------------
    // 场景 7：控制台无未捕获异常、无 404 静态资源
    // ---------------------------------------------------------------------
    await t.test('场景7：无未捕获异常与静态资源 404', async () => {
      assert.deepEqual(browser.consoleExceptions, [], '控制台不应有未捕获异常');
      assert.deepEqual([...new Set(browser.staticResourceFailures)], [], '不应有失败的静态资源请求');
    });

    // 诊断信息：合成 API 未匹配路径（不应包含设备相关端点）。
    const unknownDeviceCalls = app.state.unknownApiPaths.filter(call => call.includes('/devices'));
    assert.deepEqual(unknownDeviceCalls, [], '设备相关请求不应落入合成 API 的未匹配兜底');
  } finally {
    if (browser) await browser.close();
    await app.close();
  }
});
