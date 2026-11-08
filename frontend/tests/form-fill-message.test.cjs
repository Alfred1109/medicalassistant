const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

function fixture() {
  const filename = path.resolve(__dirname, '../src/services/formIntegrationService.ts');
  const compiled = ts.transpileModule(readFileSync(filename, 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS },
  });
  const module = { exports: {} };
  vm.runInNewContext(compiled.outputText, {
    module, exports: module.exports, URL,
    require(name) {
      if (name === './apiClient') return {};
      throw new Error(`Unexpected import: ${name}`);
    },
  }, { filename });
  return module.exports;
}

const embed = { embedUrl: 'https://forms.example/integration/embed/one-time', sessionUuid: 'session-1' };
const data = { source: 'form11344', type: 'fill_status', sessionSid: 'session-1', responseId: 7, status: 'submitted' };

test('only the exact iframe window and matching origin/session can report fill status', () => {
  const { isTrustedFormPlatformFillStatusEvent: trusted } = fixture();
  const frameWindow = {};
  const event = { source: frameWindow, origin: 'https://forms.example', data };
  assert.equal(trusted(event, frameWindow, embed), true);
  // A same-origin sibling, popup, or parent can copy all payload fields.
  assert.equal(trusted({ ...event, source: {} }, frameWindow, embed), false);
  assert.equal(trusted({ ...event, source: null }, frameWindow, embed), false);
  assert.equal(trusted(event, null, embed), false);
  assert.equal(trusted({ ...event, origin: 'https://attacker.example' }, frameWindow, embed), false);
  assert.equal(trusted({ ...event, data: { ...data, sessionSid: 'other-session' } }, frameWindow, embed), false);
  assert.equal(trusted(event, frameWindow, { ...embed, sessionUuid: null }), false);
});

test('malformed message or embedded URL never authorizes status handling', () => {
  const { isTrustedFormPlatformFillStatusEvent: trusted } = fixture();
  const frameWindow = {};
  const event = { source: frameWindow, origin: 'https://forms.example', data };
  for (const invalid of [null, 'submitted', { ...data, source: 'other' }, { ...data, type: 'other' }, { ...data, responseId: '7' }]) {
    assert.equal(trusted({ ...event, data: invalid }, frameWindow, embed), false);
  }
  for (const embedUrl of ['not-a-url', 'javascript:alert(1)', 'data:text/html,hello']) {
    assert.equal(trusted(event, frameWindow, { ...embed, embedUrl }), false);
  }
});
