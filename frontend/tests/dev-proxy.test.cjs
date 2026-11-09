const assert = require('node:assert/strict');
const { test } = require('node:test');
const http = require('node:http');
const { createHash } = require('node:crypto');
const path = require('node:path');
const { once } = require('node:events');

function request(port, pathname, upgrade = false) {
  return new Promise((resolve, reject) => {
    const req = http.get({ host: '127.0.0.1', port, path: pathname, headers: upgrade ? {
      Connection: 'Upgrade', Upgrade: 'websocket', 'Sec-WebSocket-Version': '13',
      'Sec-WebSocket-Key': 'dGhlIHNhbXBsZSBub25jZQ==',
    } : {} }, res => {
      let body = '';
      res.setEncoding('utf8');
      res.on('data', chunk => { body += chunk; });
      res.on('end', () => resolve({ status: res.statusCode, body }));
    });
    req.on('upgrade', (res, socket) => {
      resolve({ status: res.statusCode, headers: res.headers });
      socket.destroy();
    });
    req.on('error', reject);
    req.setTimeout(5000, () => req.destroy(new Error('proxy request timed out')));
  });
}

test('actual Vite config proxies API and WebSocket at root and deployment prefix', async t => {
  const { createServer } = await import('vite');
  const root = path.resolve(__dirname, '..');
  const previous = { prefix: process.env.VITE_API_PREFIX, target: process.env.VITE_BACKEND_TARGET };
  t.after(() => {
    for (const [key, value] of [['VITE_API_PREFIX', previous.prefix], ['VITE_BACKEND_TARGET', previous.target]]) {
      if (value === undefined) delete process.env[key]; else process.env[key] = value;
    }
  });
  for (const configuredPrefix of ['', '/medical/', '/care.v2']) {
    await t.test(configuredPrefix || 'root', async () => {
      const requests = [];
      const sockets = new Set();
      const backend = http.createServer((req, res) => {
        requests.push(req.url);
        res.setHeader('Content-Type', 'application/json');
        res.end(JSON.stringify({ url: req.url, host: req.headers.host }));
      });
      backend.on('connection', socket => {
        sockets.add(socket);
        socket.on('close', () => sockets.delete(socket));
      });
      backend.on('upgrade', (req, socket) => {
        const accept = createHash('sha1').update(req.headers['sec-websocket-key'] + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest('base64');
        socket.write('HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n' +
          `Sec-WebSocket-Accept: ${accept}\r\nX-Backend-Path: ${req.url}\r\nX-Backend-Host: ${req.headers.host}\r\n\r\n`);
      });
      backend.listen(0, '127.0.0.1');
      await once(backend, 'listening');
      process.env.VITE_API_PREFIX = configuredPrefix;
      process.env.VITE_BACKEND_TARGET = `http://127.0.0.1:${backend.address().port}`;
      let vite;
      try {
        vite = await createServer({ root, configFile: path.join(root, 'vite.config.ts'), mode: 'test',
          logLevel: 'silent', server: { port: 0, host: '127.0.0.1', hmr: false } });
        await vite.listen();
        const port = vite.httpServer.address().port;
        const prefix = configuredPrefix.replace(/\/+$/, '');
        assert.equal(vite.config.base, `${prefix}/`);
        for (const suffix of ['/api/auth/config?check=one', '/api', '/api?check=two']) {
          const result = await request(port, prefix + suffix);
          assert.equal(result.status, 200);
          assert.deepEqual(JSON.parse(result.body), { url: suffix, host: `127.0.0.1:${port}` });
        }
        const upgraded = await request(port, `${prefix}/ws/chat/test?token=synthetic`, true);
        assert.equal(upgraded.status, 101);
        assert.equal(upgraded.headers['x-backend-path'], '/ws/chat/test?token=synthetic');
        assert.equal(upgraded.headers['x-backend-host'], `127.0.0.1:${port}`);
        const before = requests.length;
        await request(port, `${prefix}/apiary`);
        await request(port, `${prefix}x/api/auth/config`);
        assert.equal(requests.length, before, 'similar path prefixes must not reach the backend');
      } finally {
        if (vite) await vite.close();
        for (const socket of sockets) socket.destroy();
        await new Promise(resolve => backend.close(resolve));
      }
    });
  }
});
