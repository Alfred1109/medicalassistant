const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

function fixture(document) {
  const filename = path.resolve(__dirname, '../src/services/formIntegrationService.ts');
  const compiled = ts.transpileModule(readFileSync(filename, 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS },
  });
  const module = { exports: {} };
  vm.runInNewContext(compiled.outputText, {
    module, exports: module.exports, URL, document,
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


test('launch posts credential to exact iframe and removes temporary form', () => {
  let submitted;
  const children = [];
  const document = { body: { appendChild(form) { children.push(form); } }, createElement(tag) {
    if (tag === 'input') return {};
    return { appendChild(input) { this.input = input; }, submit() { submitted = { action: this.action, method: this.method, target: this.target, token: this.input.value }; }, remove() { children.splice(children.indexOf(this), 1); } };
  } };
  const { submitFillLaunch } = fixture(document);
  const frame = { name: 'unique-frame' };
  const launch = { mode: 'launch', action: 'https://forms.example/integration/embed/session-1', token: 'synthetic-one-use', sessionUuid: 'session-1' };
  submitFillLaunch(launch, frame);
  assert.deepEqual(submitted, { action: launch.action, method: 'POST', target: frame.name, token: launch.token });
  assert.equal(children.length, 0);
  assert.equal(frame.src, undefined);
  submitFillLaunch({ mode: 'resume', url: 'https://forms.example/integration/resume/session-1', sessionUuid: 'session-1' }, frame);
  assert.equal(frame.src, 'https://forms.example/integration/resume/session-1');
  for (const action of ['http://forms.example/integration/embed/session-1', 'https://forms.example/integration/embed/other', 'https://forms.example/integration/embed/session-1?token=leak']) assert.throws(() => submitFillLaunch({ ...launch, action }, frame));
});
