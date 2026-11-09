const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {buildSync, transformSync} = require('esbuild');
const root = path.resolve(__dirname, '..');
const code = buildSync({entryPoints:[path.join(root,'src/utils/quality.ts')],bundle:true,platform:'node',format:'cjs',write:false}).outputFiles[0].text;
const loaded = {exports:{}};
vm.runInNewContext(code,{module:loaded,exports:loaded.exports,require,Date,crypto,Uint8Array});
const domain=loaded.exports;
const summary = {selected_total:1,scope_total:3,missing_date_count:1,invalid_date_count:1,unresolved_patient_count:0,by_status:[{status:'draft',count:1}]};

test('process filters include the selected local end day and preserve DST calendar boundaries',()=>{
  const previous=process.env.TZ;
  try {
    process.env.TZ='America/New_York';
    const spring=domain.qualityFilters(' patient ','2026-03-08','2026-03-08');
    assert.equal(spring.patient_id,'patient');
    assert.equal(new Date(spring.end_date)-new Date(spring.start_date),23*60*60*1000);
    const autumn=domain.qualityFilters('','2026-11-01','2026-11-01');
    assert.equal(new Date(autumn.end_date)-new Date(autumn.start_date),25*60*60*1000);
    assert.throws(()=>domain.qualityFilters('','2026-02-30',''),/日期无效/);
    assert.throws(()=>domain.qualityFilters('','2026-11-02','2026-11-01'),/结束日期/);
  } finally {if(previous===undefined)delete process.env.TZ;else process.env.TZ=previous;}
});

test('overview and facts validate exact scope and reject corrupt or foreign data',()=>{
  const overview={generated_at:'2026-11-09T00:00:00Z',scope_kind:'selected_patient',read_consistency:'independent_live_reads',publication_validation:'reference_and_required_structure',window:{},followups:{...summary,in_review_count:1},plans:{...summary,publication_states:[{state:'published',count:1}]}};
  assert.equal(domain.validQualityOverview(overview),true);
  assert.equal(domain.validQualityOverview({...overview,scope_kind:'implicit_all'}),false);
  assert.equal(domain.validQualityOverview({...overview,plans:{...overview.plans,selected_total:-1}}),false);
  const fact={source_type:'rehab_plan',source_id:'a'.repeat(24),source_reference_state:'valid',patient_id:'patient',status:'draft',date:null,date_quality:'missing',patient_reference_state:'valid',issue_eligible:true};
  const page={items:[fact],total:1,skip:0,limit:20};
  assert.equal(domain.validQualityFactPage(page,'rehab_plan',{patient_id:'patient'},0,20),true);
  assert.equal(domain.validQualityFactPage(page,'followup',{},0,20),false);
  assert.equal(domain.validQualityFactPage(page,'rehab_plan',{patient_id:'other'},0,20),false);
  assert.equal(domain.validQualityFactPage({...page,items:[{...fact,status:{private:'data'}}]},'rehab_plan',{},0,20),false);
});

test('evidence is mandatory and limited, operation identity is safe on HTTP, and navigation is allowlisted',()=>{
  assert.deepEqual(Array.from(domain.evidenceReferences(' ref-1 \nref-1\nref-2 ')),['ref-1','ref-2']);
  assert.throws(()=>domain.evidenceReferences(' \n '),/证据引用/);
  assert.throws(()=>domain.evidenceReferences('x'.repeat(257)),/证据引用/);
  assert.throws(()=>domain.evidenceReferences(Array.from({length:21},(_,i)=>String(i)).join('\n')),/证据引用/);
  assert.match(domain.qualityOperationId(),/^[0-9a-f]{32}$/);
  assert.notEqual(domain.qualityOperationId(),domain.qualityOperationId());
  assert.equal(domain.qualitySourcePath('followup','a'.repeat(24)),`/app/follow-ups/${'a'.repeat(24)}`);
  assert.equal(domain.qualitySourcePath('external','a'.repeat(24)),null);
  assert.equal(domain.qualitySourcePath('rehab_plan','https://example.com'),null);
  assert.match(domain.qualityError({response:{status:409}},'fallback'),/重新加载核对/);
});

test('quality transport sends scoped paginated reads, evidence, CAS and fixed CSV endpoint',async()=>{
  const calls=[];
  const transport=Object.fromEntries(['get','post'].map(method=>[method,async(...args)=>{calls.push({method,args});return{data:{}};} ]));
  const source=transformSync(fs.readFileSync(path.join(root,'src/services/quality.ts'),'utf8'),{loader:'ts',format:'cjs'}).code;
  const module={exports:{}};
  vm.runInNewContext(source,{module,exports:module.exports,require:()=>transport,encodeURIComponent});
  const api=module.exports.qualityApi;
  await api.facts('rehab_plan',{patient_id:'patient'},20,20,'signal');
  assert.equal(calls[0].args[0],'/quality-monitoring/plans');assert.equal(calls[0].args[1].params.patient_id,'patient');assert.equal(calls[0].args[1].params.skip,20);
  await api.report({start_date:'explicit'});assert.equal(calls[1].args[0],'/quality-monitoring/report.csv');assert.equal(calls[1].args[1].responseType,'blob');
  await api.resolve('id',{request_id:'same-key',expected_version:3,resolution:'manual',evidence_refs:['ref']});
  assert.equal(calls[2].args[1].expected_version,3);assert.equal(calls[2].args[1].request_id,'same-key');
  await api.review('id',{request_id:'review-key',expected_version:4,decision:'return',note:'manual',evidence_refs:['ref']});
  assert.equal(calls[3].args[1].decision,'return');
});
