// T76 通信附件前端契约：chatService 附件引用类型辅助与上传 API。
// 与 chat-read-receipt.test.cjs 同款打桩方式：TS 转译 + vm 沙盒，stub './api'。
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

function fixture() {
  const posts = [];
  const apiStub = {
    async post(url, body, config) {
      posts.push({ url, body, config });
      return { data: { id: 'att-1', kind: 'image', name: 'photo.png', size: 123,
        url: `/api/communications/attachments/att-1` } };
    },
  };
  const filename = path.resolve(__dirname, '../src/services/chatService.ts');
  const compiled = ts.transpileModule(readFileSync(filename, 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS },
  });
  const module = { exports: {} };
  vm.runInNewContext(compiled.outputText, {
    module, exports: module.exports,
    console, FormData, File, Blob,
    require(name) {
      if (name === './api') return { default: apiStub, __esModule: true };
      throw new Error(`Unexpected import: ${name}`);
    },
  }, { filename });
  return { ...module.exports, posts };
}

test('isImageAttachment discriminates image vs file refs (kind first, content_type fallback)', () => {
  const { isImageAttachment } = fixture();
  assert.equal(isImageAttachment({ kind: 'image', content_type: 'image/png' }), true);
  assert.equal(isImageAttachment({ kind: 'file', content_type: 'application/pdf' }), false);
  // 历史消息附件无 kind 时按 content_type 判别
  assert.equal(isImageAttachment({ content_type: 'image/jpeg' }), true);
  assert.equal(isImageAttachment({ content_type: 'application/pdf' }), false);
  assert.equal(isImageAttachment({}), false);
  assert.equal(isImageAttachment(null), false);
  assert.equal(isImageAttachment(undefined), false);
});

test('attachmentUrl prefers backend url and falls back to id-based path', () => {
  const { attachmentUrl } = fixture();
  assert.equal(attachmentUrl({ url: '/api/communications/attachments/a1' }),
    '/api/communications/attachments/a1');
  assert.equal(attachmentUrl({ id: 'a1' }), '/api/communications/attachments/a1');
  assert.equal(attachmentUrl({}), '');
  assert.equal(attachmentUrl(null), '');
});

test('formatAttachmentSize renders B/KB/MB labels', () => {
  const { formatAttachmentSize } = fixture();
  assert.equal(formatAttachmentSize(undefined), '');
  assert.equal(formatAttachmentSize(0), '');
  assert.equal(formatAttachmentSize(512), '512B');
  assert.equal(formatAttachmentSize(2048), '2.0KB');
  assert.equal(formatAttachmentSize(5 * 1024 * 1024), '5.0MB');
});

test('chatApi.uploadAttachment posts multipart FormData to the conversation endpoint', async () => {
  const { chatApi, posts } = fixture();
  const ref = await chatApi.uploadAttachment(
    'conv-1', new File([new Blob([new Uint8Array([137])])], 'photo.png', { type: 'image/png' }));
  assert.equal(posts.length, 1);
  assert.equal(posts[0].url, '/communications/conversations/conv-1/attachments');
  assert.ok(posts[0].body instanceof FormData);
  assert.equal(posts[0].body.get('file').name, 'photo.png');
  assert.equal(posts[0].config.headers['Content-Type'], 'multipart/form-data');
  assert.equal(ref.id, 'att-1');
  assert.equal(ref.kind, 'image');
});
