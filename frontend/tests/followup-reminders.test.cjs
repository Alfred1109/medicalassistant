const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const { buildSync, transformSync } = require('esbuild');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const filename=path.join(__dirname,'.followup-reminders.compiled.cjs');
const code=buildSync({stdin:{contents:"export * from './utils/followupReminders'; export {FollowUpReminderSummary} from './components/HealthManager/FollowUpReminderPanel';",resolveDir:path.resolve(__dirname,'../src'),loader:'ts'},bundle:true,platform:'node',format:'cjs',write:false,packages:'external',define:{'import.meta.env.VITE_API_URL':'undefined','import.meta.env.VITE_API_PREFIX':'undefined'},logLevel:'silent'}).outputFiles[0].text;
const loaded=new Module(filename,module);loaded.filename=filename;loaded.paths=Module._nodeModulePaths(__dirname);loaded._compile(code,filename);const domain=loaded.exports;
const runtime={enabled:true,running:true,state:'ready',last_checked_at:'2026-11-09T00:00:00',last_success_at:'2026-11-09T00:00:00',last_error_code:null};
const base={policy:'inapp-24h-v1',followup_id:'visit-1',patient_id:'patient-1',planned_at:'2026-11-10T00:00:00',checked_at:'2026-11-09T00:00:00'};
function render(props){return renderToStaticMarkup(React.createElement(domain.FollowUpReminderSummary,{runtime,history:null,runtimeError:null,historyError:null,...props}));}
test('reminder summary distinguishes both recipients and persistence from receipt',()=>{
 const html=render({history:{items:[{...base,slot:'patient',status:'persisted',notification_id:'notification-1'},{...base,slot:'provider',status:'skipped',reason:'PROVIDER_NOT_ASSIGNED'}],total:2,skip:0,limit:20}});
 for(const text of ['患者','责任医护','已生成站内通知','未生成通知','当前未分配管理该患者','不代表收件人已收到或阅读'])assert.ok(html.includes(text),text);
 assert.equal(html.includes('发送成功'),false);assert.equal(html.includes('已送达'),false);
});
test('disabled service, service error and unrecorded slots remain explicit',()=>{
 assert.ok(render({runtime:{...runtime,enabled:false,state:'disabled'}}).includes('服务未启用'));
 assert.ok(render({runtime:{...runtime,state:'error',last_error_code:'REMINDER_STORAGE_UNAVAILABLE'}}).includes('存储或事务条件不可用'));
 const html=render({history:{items:[],total:0,skip:0,limit:20}});
 assert.ok(html.includes('患者：'));assert.ok(html.includes('责任医护：'));assert.ok(html.includes('尚不能确认未生成的具体原因'));
 assert.ok(render({runtimeError:'状态无权限',history:{items:[{...base,slot:'patient',status:'persisted'}],total:1,skip:0,limit:20}}).includes('已生成站内通知'));
});
test('failed persistence limits automatic retry to before the plan time',()=>{
 const html=render({history:{items:[{...base,slot:'patient',status:'failed',reason:'PERSISTENCE_FAILED'}],total:1,skip:0,limit:20}});
 assert.ok(html.includes('生成失败，计划时间前会自动重试'));
 assert.ok(html.includes('站内通知暂未能保存，计划时间前会自动重试；已过计划时间不会补发'));
 assert.equal(html.includes('将自动重试'),false);
 assert.equal(html.includes('未识别的处理结果'),false);
 assert.equal(html.includes('>已生成站内通知<'),false);
});
test('UTC BSON timestamps are converted explicitly and unknown reasons are not guessed',()=>{
 const previous=process.env.TZ;try{process.env.TZ='Asia/Singapore';assert.equal(domain.reminderTime('2026-11-09T00:00:00'),domain.reminderTime('2026-11-09T00:00:00Z'));assert.ok(domain.reminderTime('2026-11-09T00:00:00').includes('08:00:00'));assert.equal(domain.reminderTime(null),'未记录');assert.equal(domain.reminderTime('bad'),'时间不可用');}finally{if(previous===undefined)delete process.env.TZ;else process.env.TZ=previous;}
 assert.ok(domain.reminderReason('PLAN_PASSED').includes('未补发'));assert.ok(domain.reminderReason('unknown').includes('核查'));
});
test('reminder API reads exact status and scoped paginated history with cancellation',async()=>{
 const calls=[];const file=path.resolve(__dirname,'../src/services/followupReminders.ts');const service=new Module(file,module);service.filename=file;service.paths=Module._nodeModulePaths(__dirname);service.require=name=>name==='./httpClient'?{get:async(...args)=>{calls.push(args);return{data:{}}}}:require(name);service._compile(transformSync(fs.readFileSync(file,'utf8'),{loader:'ts',format:'cjs'}).code,file);
 const signal=new AbortController().signal;await service.exports.followupReminders.status(signal);await service.exports.followupReminders.history('visit-1',20,20,signal);
 assert.deepEqual(calls,[['/health-records/followup-reminders/status',{signal}],['/health-records/followup-reminders',{params:{followup_id:'visit-1',skip:20,limit:20},signal}]]);
});
