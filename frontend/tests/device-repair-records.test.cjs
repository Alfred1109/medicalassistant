const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const { transformSync } = require('esbuild');

const root = path.resolve(__dirname, '..');
const loadService = (transport) => {
  const file = path.resolve(root, 'src/services/deviceRepairService.ts');
  const compiled = new Module(file, module);
  compiled.filename = file;
  compiled.paths = Module._nodeModulePaths(__dirname);
  compiled.require = name => name === './httpClient' ? transport : require(name);
  compiled._compile(transformSync(fs.readFileSync(file, 'utf8'), { loader: 'ts', format: 'cjs' }).code, file);
  return compiled.exports;
};

test('repair service consumes the read-only device-repairs endpoints verbatim', async () => {
  const calls = [];
  const transport = { get: async (...args) => { calls.push(args); return { data: [] }; } };
  const { deviceRepairService } = loadService(transport);
  await deviceRepairService.listHistory({ deviceId: 'device-1', success: false, days: 7, limit: 100 });
  await deviceRepairService.listHistory({});
  await deviceRepairService.getDetail('repair-9');
  await deviceRepairService.getDeviceSummary('device-1', 90);
  assert.deepEqual(calls, [
    ['/device-repairs/history', { params: { device_id: 'device-1', success: false, days: 7, limit: 100 } }],
    ['/device-repairs/history', { params: { device_id: undefined, success: undefined, days: undefined, limit: undefined } }],
    ['/device-repairs/repair-9'],
    ['/device-repairs/device/device-1/summary', { params: { days: 90 } }],
  ]);
});

test('the repair adapter is strictly read-only because the backend has no write endpoints', () => {
  const source = fs.readFileSync(path.join(root, 'src/services/deviceRepairService.ts'), 'utf8');
  assert.match(source, /只读/);
  assert.doesNotMatch(source, /\.post\(|\.put\(|\.patch\(|\.delete\(/);
});

test('device management hosts the repair records tab without a create entry', () => {
  const page = fs.readFileSync(path.join(root, 'src/pages/Admin/DeviceManagement.tsx'), 'utf8');
  assert.match(page, /维修记录/);
  assert.match(page, /DeviceRepairRecords/);
  assert.match(page, /设备列表/);
  const panel = fs.readFileSync(path.join(root, 'src/components/Devices/DeviceRepairRecords.tsx'), 'utf8');
  // 列表/详情/统计三个后端能力都有消费入口
  assert.match(panel, /listHistory/);
  assert.match(panel, /getDetail/);
  assert.match(panel, /getDeviceSummary/);
  // 后端无登记端点，前端如实不提供新建登记
  assert.match(panel, /无手工登记入口|没有维修登记/);
  assert.doesNotMatch(panel, /\.post\(|\.put\(|\.delete\(/);
});
