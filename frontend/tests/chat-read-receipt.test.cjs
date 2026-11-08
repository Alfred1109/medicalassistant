const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

function fixture() {
  const sockets = [];
  class Socket {
    static OPEN = 1;
    constructor() { this.readyState = 1; sockets.push(this); }
    close() {}
  }
  const filename = path.resolve(__dirname, '../src/services/chatWsService.ts');
  const compiled = ts.transpileModule(readFileSync(filename, 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS },
  });
  const module = { exports: {} };
  vm.runInNewContext(compiled.outputText, {
    module, exports: module.exports, WebSocket: Socket,
    localStorage: { getItem: () => 'test-token' },
    window: { location: { origin: 'http://localhost' }, setTimeout, clearTimeout },
    require(name) {
      if (name === '../config/api') return { API_BASE_URL: 'http://localhost/api' };
      if (name === '../config/constants') return { STORAGE_KEYS: { TOKEN: 'token' } };
      throw new Error(`Unexpected import: ${name}`);
    },
  }, { filename });
  return { ...module.exports, sockets };
}
const receipt = { type: 'read_receipt', conversation_id: 'conversation', reader_id: 'patient',
  message_ids: ['own'], read_at: '2026-11-08T01:02:03.000Z' };

test('real WS client validates and dispatches persisted receipts to the page update', () => {
  const { ChatWsClient, applyChatReadReceipt, sockets } = fixture();
  let messages = [
    { id: 'own', conversation_id: 'conversation', sender_id: 'doctor', recipient_id: 'patient', read: false },
    { id: 'other', conversation_id: 'conversation', sender_id: 'doctor', recipient_id: 'patient', read: false },
    { id: 'incoming', conversation_id: 'conversation', sender_id: 'patient', recipient_id: 'doctor', read: false },
  ];
  let callbacks = 0;
  const client = new ChatWsClient({ onReadReceipt(event) {
    callbacks++;
    messages = applyChatReadReceipt(messages, event, 'conversation', 'doctor');
  } });
  client.connect('conversation');
  sockets[0].onmessage({ data: JSON.stringify(receipt) });
  assert.equal(callbacks, 1);
  assert.equal(messages[0].read, true);
  assert.equal(messages[0].read_at, receipt.read_at);
  assert.equal(messages[1].read, false);
  assert.equal(messages[2].read, false);
  for (const invalid of [{ ...receipt, message_ids: [42] }, { ...receipt, read_at: 'invalid' },
    { ...receipt, reader_id: null }]) {
    sockets[0].onmessage({ data: JSON.stringify(invalid) });
  }
  assert.equal(callbacks, 1);
  client.disconnect();
});

test('receipt from another conversation or the current user cannot mark outgoing messages', () => {
  const { applyChatReadReceipt } = fixture();
  const messages = [{ id: 'own', conversation_id: 'conversation', sender_id: 'doctor', recipient_id: 'patient', read: false }];
  assert.equal(applyChatReadReceipt(messages, receipt, 'different', 'doctor'), messages);
  assert.equal(applyChatReadReceipt(messages, { ...receipt, reader_id: 'doctor' }, 'conversation', 'doctor'), messages);
});
