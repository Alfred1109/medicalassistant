const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
let component;
let session = { role: 'patient', identityConfirmed: true, user: { id: 'p', role: 'patient' } };
const calls = [];
const wx = { navigateBack({ delta, success }) { calls.push(['back', delta]); success(); }, navigateTo({ url }) { calls.push(['to', url]); } };
const context = {
  wx, Component(value) { component = value; }, getCurrentPages() { return [{}, {}]; },
  require(name) { if (name === '../../services/api') return { getSession: () => session }; throw new Error(name); },
};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../miniprogram/components/role-nav/index.js'), 'utf8'), context);
const c = { data: { items: [], current: 'home' }, setData(values) { Object.assign(this.data, values); }, ...component.methods };
c.refresh();
assert.deepEqual(Array.from(c.data.items, item => item.label), ['首页', '康复', '健康', '消息', '我的']);
c.navigate({ currentTarget: { dataset: { key: 'plans' } } });
assert.deepEqual(calls, [['back', 1], ['to', '/pages/patient/plans/index']]);
session = { role: 'doctor', identityConfirmed: true, user: { id: 'd', role: 'doctor' } };
c.refresh();
assert.deepEqual(Array.from(c.data.items, item => item.label), ['工作台', '患者', '随访', '消息', '我的']);
session = null;
c.refresh();
assert.equal(c.data.items.length, 0);
console.log('PASS: role navigation and logout visibility');
