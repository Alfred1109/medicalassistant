const test=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const Module=require('node:module');
const {buildSync}=require('esbuild');
const root=path.resolve(__dirname,'..');
const compiled=buildSync({stdin:{contents:"export {validPatientPlan,validPatientFeedback,feedbackReference} from './src/pages/RehabPlan/PatientPlans';",resolveDir:root,loader:'ts'},bundle:true,platform:'node',format:'cjs',write:false,packages:'external',define:{'import.meta.env.VITE_API_URL':'undefined','import.meta.env.VITE_API_PREFIX':'undefined'},logLevel:'silent'}).outputFiles[0].text;
const loaded=new Module(path.join(root,'test-patient-view.cjs'));
loaded.filename=path.join(root,'test-patient-view.cjs');loaded.paths=module.paths;
loaded._compile(compiled,loaded.filename);
const view=loaded.exports;
const plan={id:'100000000000000000000001',version_id:'200000000000000000000001',publication_revision:1,published_at:'2026-11-09T08:00:00Z',content:{name:'医护已发布方案'},items:[{item_id:'300000000000000000000001',intervention_type:'diet',name:'饮食甲'}]};
const report={id:'400000000000000000000001',plan_id:plan.id,version_id:plan.version_id,prescription_item_id:plan.items[0].item_id,recorded_by:'patient-a',execution_status:'partial',feelings:'合成自述',performed_at:'2026-11-09T08:00:00Z'};

test('patient display rejects malformed or wrong-plan publication instead of rendering it',()=>{
  assert.equal(view.validPatientPlan(plan,plan.id),true);
  for(const invalid of [{...plan,id:'100000000000000000000099'},{...plan,content:null},{...plan,items:[{...plan.items[0],intervention_type:'diagnosis'}]},{...plan,version_id:'wrong'}]) assert.equal(view.validPatientPlan(invalid,plan.id),false);
});

test('history requires exact plan, account, version, item and explicit patient status',()=>{
  assert.equal(view.validPatientFeedback(report,plan.id,'patient-a'),true);
  for(const invalid of [{...report,plan_id:'other'},{...report,recorded_by:'patient-b'},{...report,version_id:'bad'},{...report,prescription_item_id:'bad'},{...report,execution_status:'diagnosed'}]) assert.equal(view.validPatientFeedback(invalid,plan.id,'patient-a'),false);
});

test('old feedback keeps historical version and item references instead of current titles',()=>{
  assert.equal(view.feedbackReference(report,plan),'当前发布方案 · 饮食 · 饮食甲');
  const historical={...report,version_id:'200000000000000000000002',prescription_item_id:'300000000000000000000002'};
  const label=view.feedbackReference(historical,plan);
  assert.match(label,/历史发布版本 200000000000000000000002/);
  assert.match(label,/处方 300000000000000000000002/);
  assert.doesNotMatch(label,/饮食甲/);
});

test('patient adapters use restricted publication and feedback endpoints with same body and cancellation',async()=>{
  const code=buildSync({entryPoints:[path.join(root,'src/services/rehabPublications.ts')],bundle:false,platform:'node',format:'cjs',write:false,logLevel:'silent'}).outputFiles[0].text;
  const calls=[];
  const transport={get:async(...args)=>{calls.push(['get',...args]);return {data:{}}},post:async(...args)=>{calls.push(['post',...args]);return {data:{}}}};
  const service=new Module(path.join(root,'test-patient-adapter.cjs'));
  service.filename=path.join(root,'test-patient-adapter.cjs');service.paths=module.paths;
  service.require=name=>name==='./httpClient'?transport:require(name);
  service._compile(code,service.filename);
  const api=service.exports.rehabPublications;
  const controller=new AbortController();
  await api.myPlans(20,20,controller.signal);await api.myPlan(plan.id,controller.signal);
  const body={event_id:'fixed-key',version_id:plan.version_id,prescription_item_id:plan.items[0].item_id,execution_status:'partial',feelings:'感受',performed_at:'2026-11-09T08:00:00Z'};
  await api.submitFeedback(plan.id,body);await api.submitFeedback(plan.id,body);await api.feedback(plan.id,0,20,controller.signal);
  assert.equal(calls[0][1],'/rehabilitation/publications/my-plans');
  assert.deepEqual(calls[0][2].params,{skip:20,limit:20});
  assert.equal(calls[1][1],'/rehabilitation/publications/my-plans/'+plan.id);
  assert.equal(calls[2][1],'/rehabilitation/plans/'+plan.id+'/patient-feedback');
  assert.deepEqual(calls[2][2],calls[3][2]);assert.equal(calls[4][2].signal,controller.signal);
});
