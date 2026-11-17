const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

let definition;
let session = {
  identityConfirmed: true,
  role: 'patient',
  sessionId: 1,
  user: { id: 'patient-1', role: 'patient' },
};
const requests = [];
const api = {
  getSession: () => session,
  clearSession() { session = null; },
  async request(url) { requests.push(url); return []; },
};
const context = {
  Page(value) { definition = value; },
  require(name) {
    if (name === '../../../services/api') return api;
    throw new Error(`Unexpected dependency: ${name}`);
  },
  console,
  Date,
  setTimeout,
  clearTimeout,
  setInterval,
  clearInterval,
};

vm.runInNewContext(
  fs.readFileSync(path.join(__dirname, '../miniprogram/pages/messages/index/index.js'), 'utf8'),
  context,
);

function createPage() {
  const page = {
    data: JSON.parse(JSON.stringify(definition.data)),
    setData(values) { Object.assign(this.data, values); },
  };
  Object.assign(page, definition);
  return page;
}

async function flush() {
  await new Promise(resolve => setImmediate(resolve));
}

(async () => {
  const page = createPage();
  page.loadSession();
  await flush();
  page.setData({ activeId: 'conversation-1', draft: 'unsent text', canSend: true });
  page.setActiveConversation({
    id: 'conversation-1',
    can_send: false,
    send_block_reason: 'care_relationship_ended',
  });

  assert.equal(page.data.sendAllowed, false);
  assert.equal(page.data.canSend, false);
  assert.equal(page.data.draft, '', 'revocation clears a draft typed before the status refresh');
  assert.match(page.data.activeConversation.send_status_text, /历史消息仍可查看/);
  const requestCount = requests.length;
  await page.sendMessage();
  assert.equal(requests.length, requestCount, 'client does not issue a send for a read-only conversation');
  page.setActiveConversation({ id: 'conversation-1' });
  assert.equal(page.data.sendAllowed, false, 'missing authorization status must fail closed');

  session = {
    identityConfirmed: true,
    role: 'doctor',
    sessionId: 2,
    user: { id: 'doctor-2', role: 'doctor' },
  };
  page.loadSession();
  await flush();
  assert.equal(page.data.session.user.id, 'doctor-2');
  assert.equal(page.data.activeId, '', 'a new session cannot inherit the previous conversation');
  assert.equal(page.data.activeConversation, null);
  assert.equal(page.data.sendAllowed, false);
  assert.equal(page.data.messages.length, 0);

  const template = fs.readFileSync(
    path.join(__dirname, '../miniprogram/pages/messages/index/index.wxml'), 'utf8');
  assert.match(template, /activeConversation\.can_send === false/);
  assert.match(template, /activeConversation\.send_status_text/);
  console.log('PASS: revoked care conversations are read-only and state is session-scoped');
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
