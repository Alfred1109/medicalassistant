const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const Module = require('node:module');
const { buildSync } = require('esbuild');

const source = path.resolve(__dirname, '../src/utils/patientSelfQuestionnaire.ts');
const bundle = buildSync({ entryPoints: [source], bundle: true, write: false, platform: 'node', format: 'cjs' });
const loaded = new Module(source);
loaded._compile(bundle.outputFiles[0].text, source);
const { patientSelfBridgeUrl } = loaded.exports;

const origin = 'https://care.test';
const api = '/medical/api';
const bridge = `${origin}${api}/integrations/forms/patient-self/launch-bridge/`;
const ticket = 'a'.repeat(43);
const taskId = '1'.repeat(24);
const result = { taskId, allowedOrigin: origin, webviewUrl: bridge + ticket };

test('accepts the current task bridge under the configured application prefix', () => {
  assert.equal(patientSelfBridgeUrl(result, taskId, origin, api).href, result.webviewUrl);
});

test('refuses cross-site and mismatched task navigation and ticket-bearing queries', () => {
  const failures = [
    { ...result, taskId: '2'.repeat(24) },
    { ...result, allowedOrigin: 'https://other.test' },
    { ...result, webviewUrl: `${bridge}${ticket}?session=old` },
    { ...result, webviewUrl: `${bridge}${ticket}#other` },
    { ...result, webviewUrl: bridge.replace('/medical/', '/other/') + ticket },
    { ...result, webviewUrl: bridge.replace('https://', 'http://') + ticket },
    { ...result, webviewUrl: bridge.replace('care.test', 'user:pass@care.test') + ticket },
    { ...result, webviewUrl: bridge + 'under/another-path' },
    { ...result, webviewUrl: bridge + 'short-ticket' },
  ];
  for (const invalid of failures) assert.throws(() => patientSelfBridgeUrl(invalid, taskId, origin, api));
  assert.throws(() => patientSelfBridgeUrl(result, taskId, origin, 'https://other.test/medical/api'));
});
