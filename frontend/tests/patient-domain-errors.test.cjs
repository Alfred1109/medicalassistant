const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');
const axios = require('axios');

// 与 http-client.test.cjs 相同的加载方式：TS 转译后在 vm 沙箱内执行，
// 仅替换外部依赖（axios / 配置），httpClient、patientErrors、utils 均为真实源码。
function loadModule(name, dir = 'services', cache) {
  const cachedKey = `${dir}/${name}`;
  if (cache && cache.has(cachedKey)) return cache.get(cachedKey);
  const filename = path.resolve(__dirname, `../src/${dir}/${name}.ts`);
  const compiled = ts.transpileModule(readFileSync(filename, 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, esModuleInterop: true },
  });
  const module = { exports: {} };
  const localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
  const window = { location: { pathname: '/app/doctor/patients', href: '', origin: 'https://rehab.example', protocol: 'https:' } };
  vm.runInNewContext(compiled.outputText, {
    module, exports: module.exports, localStorage, window, console, Date,
    require(specifier) {
      if (specifier === 'axios') return { create: axios.create, get: async () => ({ data: { mode: 'legacy' } }) };
      if (specifier === '../config/apiPaths') return { API_COLLECTION_PATHS: { AGENTS: '/agents/', NOTIFICATIONS: '/notifications/', DEVICES: '/devices/' } };
      if (specifier === '../config/api') return { API_BASE_URL: '/deployment/api' };
      if (specifier === '../config/constants') return { API_BASE_URL: '/deployment/api', API_PREFIX: '/deployment', STORAGE_KEYS: { TOKEN: 'token', REFRESH_TOKEN: 'refresh_token', USER: 'user', TOKEN_EXPIRY: 'token_expiry' } };
      if (specifier === '../services/rehabClinicalWorkbench') return {}; // 仅类型引用，转译后已消除
      if (specifier === '../types/quality' || specifier.startsWith('../types/')) return {};
      if (specifier === '../services/patientErrors') return loadModule('patientErrors', 'services', cache);
      if (specifier.startsWith('./')) return loadModule(specifier.slice(2), dir, cache);
      throw new Error(`unexpected module ${specifier}`);
    },
  }, { filename });
  cache.set(cachedKey, module.exports);
  return module.exports;
}

function fixture(cache = new Map()) {
  const http = loadModule('httpClient', 'services', cache).default;
  const client = loadModule('apiClient', 'services', cache).default;
  const api = loadModule('api', 'services', cache).default;
  return { http, client, api };
}

function serverError(status, data, config) {
  return new axios.AxiosError(`Request failed with status code ${status}`, 'ERR_BAD_REQUEST',
    config, null, { status, data });
}

const PATIENT_DOMAIN_ERROR_COPY = loadModule('patientErrors', 'services', new Map()).PATIENT_DOMAIN_ERROR_COPY;
const GENERIC_503_MESSAGE = 'Request failed with status code 503';

test('patient error copy table covers every backend patient-domain code with Chinese copy', () => {
  for (const [code, copy] of Object.entries(PATIENT_DOMAIN_ERROR_COPY)) {
    assert.match(code, /^[A-Z][A-Z_]+$/);
    assert.ok(copy.length >= 10, `${code} 的提示文案过短`);
    assert.equal(copy, copy.trim());
    assert.ok(/。$/.test(copy), `${code} 的提示文案应以中文句号结尾`);
    // 文案应为纯中文提示，不暴露英文错误码或堆栈信息
    assert.ok(!/[a-z_]{6,}/.test(copy), `${code} 的提示文案不应包含英文错误码`);
  }
  assert.ok(PATIENT_DOMAIN_ERROR_COPY.PATIENT_IDENTITY_AMBIGUOUS.includes('患者档案标识存在歧义'));
});

test('response interceptor rewrites 503 PATIENT_IDENTITY_AMBIGUOUS for response and data-only callers', async () => {
  const f = fixture();
  const body = { error: 'PATIENT_IDENTITY_AMBIGUOUS', message: '患者标识对应多个实体，请先核实', details: null, request_id: 'req-1' };
  const thrown = [];
  f.http.defaults.adapter = async config => { const error = serverError(503, body, config); thrown.push(error); throw error; };
  const responseFailure = await f.api.get('/doctors/patients').then(() => null, error => error);
  const dataFailure = await f.client.get('/health-records/followup-workbench').then(() => null, error => error);
  assert.equal(thrown.length, 2);
  // 错误对象身份保持不变（拦截器就地改写，不替换错误对象）
  assert.equal(responseFailure, thrown[0]);
  assert.equal(dataFailure, thrown[1]);
  for (const error of thrown) {
    assert.equal(error.message, PATIENT_DOMAIN_ERROR_COPY.PATIENT_IDENTITY_AMBIGUOUS);
    // 响应体保持后端原样，状态码不变化
    assert.equal(error.response.status, 503);
    assert.equal(error.response.data.error, 'PATIENT_IDENTITY_AMBIGUOUS');
    assert.equal(error.response.data.message, '患者标识对应多个实体，请先核实');
  }
});

test('every patient-domain code maps through the interceptor without touching other errors', async () => {
  for (const [code, copy] of Object.entries(PATIENT_DOMAIN_ERROR_COPY)) {
    const f = fixture();
    f.http.defaults.adapter = async config => { throw serverError(503, { error: code, message: 'backend message' }, config); };
    const error = await f.client.get('/one').then(() => null, failure => failure);
    assert.equal(error.message, copy, `${code} 应映射为统一文案`);
    assert.equal(error.response.status, 503);
  }
  // 非患者域错误保持 axios 原始 message 与错误身份
  const f = fixture();
  for (const [status, data] of [[503, { detail: 'unrelated' }], [503, { error: 'OTHER_DOMAIN_CODE', message: 'x' }], [403, { error: 'PATIENT_NOT_ASSIGNED', message: 'denied' }]]) {
    const failures = [];
    f.http.defaults.adapter = async config => { const error = serverError(status, data, config); failures.push(error); throw error; };
    const error = await f.api.get('/one').then(() => null, failure => failure);
    assert.equal(error, failures[0]);
    assert.equal(error.message, `Request failed with status code ${status}`);
    assert.equal(error.response.status, status);
  }
});

test('patientDomainErrorCopy maps axios-shaped errors and ignores unrelated failures', () => {
  const cache = new Map();
  const { patientDomainErrorCopy, applyPatientDomainErrorCopy } = loadModule('patientErrors', 'services', cache);
  const ambiguous = serverError(503, { error: 'PATIENT_IDENTITY_AMBIGUOUS' }, {});
  assert.equal(patientDomainErrorCopy(ambiguous), PATIENT_DOMAIN_ERROR_COPY.PATIENT_IDENTITY_AMBIGUOUS);
  for (const code of ['QUALITY_PATIENT_SCOPE_UNVERIFIED', 'REMINDER_PATIENT_DOMAIN_UNSUPPORTED', 'REHAB_PATIENT_DOMAIN_UNSUPPORTED']) {
    assert.equal(patientDomainErrorCopy(serverError(503, { error: code }, {})), PATIENT_DOMAIN_ERROR_COPY[code]);
  }
  assert.equal(patientDomainErrorCopy(serverError(503, { error: 'UNKNOWN_CODE' }, {})), null);
  assert.equal(patientDomainErrorCopy(serverError(409, { error: 'PATIENT_IDENTITY_AMBIGUOUS' }, {})), null);
  assert.equal(patientDomainErrorCopy(new Error('普通错误')), null);
  assert.equal(patientDomainErrorCopy(null), null);
  assert.equal(patientDomainErrorCopy(undefined), null);
  // applyPatientDomainErrorCopy 就地改写 message 且保持对象身份
  const target = { message: GENERIC_503_MESSAGE, response: { status: 503, data: { error: 'REHAB_PATIENT_DOMAIN_UNSUPPORTED' } } };
  assert.equal(applyPatientDomainErrorCopy(target), target);
  assert.equal(target.message, PATIENT_DOMAIN_ERROR_COPY.REHAB_PATIENT_DOMAIN_UNSUPPORTED);
  const untouched = { message: GENERIC_503_MESSAGE };
  assert.equal(applyPatientDomainErrorCopy(untouched), untouched);
  assert.equal(untouched.message, GENERIC_503_MESSAGE);
});

test('quality and rehab workbench error helpers prefer patient-domain copy but keep status semantics', () => {
  const cache = new Map();
  const { qualityError } = loadModule('quality', 'utils', cache);
  const { workbenchError } = loadModule('rehabClinicalWorkbench', 'utils', cache);
  const scopeUnverified = serverError(503, { error: 'QUALITY_PATIENT_SCOPE_UNVERIFIED', message: '患者身份存在歧义，请先核实范围' }, {});
  assert.equal(qualityError(scopeUnverified, '兜底文案'), PATIENT_DOMAIN_ERROR_COPY.QUALITY_PATIENT_SCOPE_UNVERIFIED);
  const rehabUnsupported = serverError(503, { error: 'REHAB_PATIENT_DOMAIN_UNSUPPORTED', message: '当前患者档案尚未接入康复账号解析' }, {});
  assert.equal(workbenchError(rehabUnsupported, '兜底文案'), PATIENT_DOMAIN_ERROR_COPY.REHAB_PATIENT_DOMAIN_UNSUPPORTED);
  // 非 503 患者域语义维持既有 409/403 文案，不被患者域映射覆盖
  assert.equal(qualityError(serverError(409, { detail: 'conflict' }, {}), '兜底文案'), '记录已变化或本次请求发生冲突，请重新加载核对后再操作。');
  assert.equal(qualityError(serverError(403, { detail: 'denied' }, {}), '兜底文案'), '当前账号无权查看或处理这些记录。');
  assert.equal(workbenchError(serverError(409, { detail: 'conflict' }, {}), '兜底文案'), '方案已更新或本次操作发生冲突。请重新加载核对后再操作。');
  assert.equal(workbenchError(serverError(403, { detail: 'denied' }, {}), '兜底文案'), '当前已无权管理该患者的方案。');
  // 普通错误回退原有 message / detail / fallback 路径
  assert.equal(qualityError(serverError(503, { error: 'OTHER', message: '后端消息' }, {}), '兜底文案'), '后端消息');
  assert.equal(workbenchError(serverError(500, { detail: '服务异常' }, {}), '兜底文案'), '服务异常');
  assert.equal(workbenchError(new Error('本地错误'), '兜底文案'), '兜底文案');
});

test('legacy authentication flow still rejects with untouched non-patient-domain 401', async () => {
  const f = fixture();
  // 401 未携带患者域错误码时不改写错误内容
  f.http.defaults.adapter = async config => { throw serverError(401, { error: 'INVALID_TOKEN', message: '无效的认证令牌' }, config); };
  const error = await f.client.get('/one').then(() => null, failure => failure);
  assert.equal(error.message, GENERIC_401_MESSAGE);
  assert.equal(error.response.data.error, 'INVALID_TOKEN');
});

const GENERIC_401_MESSAGE = 'Request failed with status code 401';
