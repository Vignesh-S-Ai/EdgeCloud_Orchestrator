import json,time,urllib.request,datetime,statistics
U='http://127.0.0.1:8002/decision'
def m(c,r,d): return {'cpu_percent':c,'ram_percent':r,'disk_percent':d,'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat()}
def p(priority='low',ec=10,er=20,ed=20,cc=15,cr=25,cd=30,lat=30,wid='o55'):
 return {'workload':{'workload_id':wid,'priority':priority,'workload_type':'object_detection','latency_requirement_ms':100},'edge_metrics':m(ec,er,ed),'cloud_metrics':m(cc,cr,cd),'network_metrics':{'latency_ms':lat,'bandwidth_mbps':100}}
def call(b):
 t=time.perf_counter(); q=urllib.request.Request(U,data=json.dumps(b).encode(),headers={'Content-Type':'application/json'})
 try:
  with urllib.request.urlopen(q,timeout=8) as x: status=x.status; out=json.loads(x.read())
  return status,out.get('target'),out.get('reason',''),round((time.perf_counter()-t)*1000,3),None
 except Exception as e: return getattr(e,'code',0) or 0,None,'',round((time.perf_counter()-t)*1000,3),str(e)
thresholds={'low':70.0,'medium':75.0,'high':85.0}
cases=[]
for pr,thr in thresholds.items():
 for label,v,expected in [('below',thr-0.1,'edge'),('at',thr,'edge'),('above',thr+0.1,'cloud')]:
  cases.append((f'{pr} CPU {label} threshold',p(priority=pr,ec=v),expected))
 for label,v,expected in [('below',thr-0.1,'edge'),('at',thr,'edge'),('above',thr+0.1,'cloud')]:
  cases.append((f'{pr} RAM {label} threshold',p(priority=pr,er=v),expected))
 for label,v,expected in [('disk at 85',85.0,'edge'),('disk above 85',85.1,'cloud')]:
  cases.append((f'{pr} {label}',p(priority=pr,ed=v),expected))
for pr,thr in thresholds.items():
 expected='edge' if pr=='high' else 'queue'
 cases.append((f'{pr} priority with poor network',p(priority=pr,ec=thr+0.1,lat=500),expected))
raw=[]; start=time.perf_counter()
for name,b,exp in cases:
 for rep in range(1,6):
  b=json.loads(json.dumps(b)); b['workload']['workload_id']=f'{name}-{rep}'
  status,actual,reason,lat,err=call(b)
  raw.append({'scenario':name,'repeat':rep,'priority':b['workload']['priority'],'expected':exp,'actual':actual,'status':status,'latency_ms':lat,'reason':reason,'error':err})
trans=[]
for pr,thr in thresholds.items():
 for i,delta in enumerate([-0.1,0.1,-0.1,0.1,0.0,0.1],1):
  cpu=thr+delta; b=p(priority=pr,ec=cpu,wid=f'{pr}-jitter-{i}')
  status,actual,reason,lat,err=call(b)
  trans.append({'priority':pr,'step':i,'edge_cpu_percent':cpu,'expected':'edge' if delta<=0 else 'cloud','actual':actual,'status':status,'latency_ms':lat,'reason':reason,'error':err})
summary=[]
for name,b,exp in cases:
 rr=[x for x in raw if x['scenario']==name]; ls=sorted(x['latency_ms'] for x in rr)
 summary.append({'scenario':name,'priority':b['workload']['priority'],'expected':exp,'requests':len(rr),'http_200':sum(x['status']==200 for x in rr),'expected_matches':sum(x['actual']==exp for x in rr),'actual_counts':{v:sum(x['actual']==v for x in rr) for v in ['edge','cloud','queue','error']},'mean_api_latency_ms':round(statistics.mean(ls),3),'p95_api_latency_ms':ls[4]})
res={'milestone':'O5.5','title':'Scheduler Decision Stability and Priority-Aware Validation','tested_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'endpoint':U,'policy':'rule_based','method':'Live scheduler API with synthetic metric snapshots. Five repetitions per static scenario plus threshold jitter sequences for Low, Medium, and High priorities. No inference workloads or deployment changes.','priority_thresholds':thresholds,'scenario_count':len(cases),'scenario_requests':len(raw),'jitter_requests':len(trans),'total_requests':len(raw)+len(trans),'http_200_count':sum(x['status']==200 for x in raw+trans),'all_expected_matches':all(x['actual']==x['expected'] for x in raw+trans),'all_http_success':all(x['status']==200 for x in raw+trans),'scenario_summary':summary,'jitter_sequences':trans,'raw_records':raw,'duration_sec':round(time.perf_counter()-start,3)}
print('O55_RESULT_BEGIN'); print(json.dumps(res,separators=(',',':'))); print('O55_RESULT_END')
