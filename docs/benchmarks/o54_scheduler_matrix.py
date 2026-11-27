import json,time,urllib.request,datetime,statistics
U='http://127.0.0.1:8002/decision'
def m(c,r,d): return {'cpu_percent':c,'ram_percent':r,'disk_percent':d,'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat()}
def p(ec=10,er=20,ed=20,cc=15,cr=25,cd=30,lat=30,pr='low'):
 return {'workload':{'workload_id':'o54','priority':pr,'workload_type':'object_detection','latency_requirement_ms':100},'edge_metrics':m(ec,er,ed),'cloud_metrics':m(cc,cr,cd),'network_metrics':{'latency_ms':lat,'bandwidth_mbps':100}}
cases=[('healthy',p(),'edge'),('CPU69',p(ec=69),'edge'),('CPU70',p(ec=70),'edge'),('CPU70.1',p(ec=70.1),'cloud'),('CPU95',p(ec=95),'cloud'),('RAM69',p(er=69),'edge'),('RAM70',p(er=70),'edge'),('RAM70.1',p(er=70.1),'cloud'),('Disk85',p(ed=85),'edge'),('Disk85.1',p(ed=85.1),'cloud'),('CloudCPU80',p(ec=71,cc=80),'cloud'),('CloudCPU80.1',p(ec=71,cc=80.1),'error'),('Cloud saturated Edge healthy',p(cc=80.1),'edge'),('Both saturated',p(ec=71,cc=80.1),'error'),('Latency200',p(ec=71,lat=200),'cloud'),('Latency200.1',p(ec=71,lat=200.1),'queue'),('High poor network',p(ec=86,lat=500,pr='high'),'edge'),('Medium poor network',p(ec=86,lat=500,pr='medium'),'queue'),('RAM80',p(er=80),'cloud')]
def call(b):
 t=time.perf_counter(); q=urllib.request.Request(U,data=json.dumps(b).encode(),headers={'Content-Type':'application/json'})
 try:
  with urllib.request.urlopen(q,timeout=8) as x: status=x.status; out=json.loads(x.read())
  return status,out.get('target'),out.get('reason',''),round((time.perf_counter()-t)*1000,3),None
 except Exception as e: return getattr(e,'code',0) or 0,None,'',round((time.perf_counter()-t)*1000,3),str(e)
raw=[]; start=time.perf_counter()
for name,b,exp in cases:
 for rep in range(1,6):
  b=json.loads(json.dumps(b)); b['workload']['workload_id']=name+'-'+str(rep)
  status,actual,reason,lat,err=call(b); raw.append({'scenario':name,'repeat':rep,'expected':exp,'actual':actual,'status':status,'latency_ms':lat,'reason':reason,'error':err})
trans=[]
for i,cpu in enumerate([20,45,65,69,70,70.1,75,85,95,65,40,20],1):
 b=p(ec=cpu); b['workload']['workload_id']='transition-'+str(i)
 status,actual,reason,lat,err=call(b); trans.append({'step':i,'edge_cpu':cpu,'expected':'edge' if cpu<=70 else 'cloud','actual':actual,'status':status,'latency_ms':lat,'reason':reason,'error':err})
summary=[]
for name,b,exp in cases:
 rr=[x for x in raw if x['scenario']==name]; ls=sorted(x['latency_ms'] for x in rr)
 summary.append({'scenario':name,'expected':exp,'requests':len(rr),'http_200':sum(x['status']==200 for x in rr),'matches':sum(x['actual']==exp for x in rr),'targets':{v:sum(x['actual']==v for x in rr) for v in ['edge','cloud','queue','error']},'mean_ms':round(statistics.mean(ls),3),'p95_ms':ls[4]})
res={'milestone':'O5.4','tested_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'endpoint':U,'policy':'rule_based','method':'Live scheduler API; synthetic metrics; five repeats per scenario and sequential CPU transition series. No inference workload or deployment changes.','scenario_count':len(cases),'scenario_requests':len(raw),'transition_requests':len(trans),'total_requests':len(raw)+len(trans),'http_200_count':sum(x['status']==200 for x in raw+trans),'all_expected_matches':all(x['actual']==x['expected'] for x in raw+trans),'all_http_success':all(x['status']==200 for x in raw+trans),'summary':summary,'transition_sequence':trans,'raw_records':raw,'duration_sec':round(time.perf_counter()-start,3)}
print('O54_RESULT_BEGIN'); print(json.dumps(res,separators=(',',':'))); print('O54_RESULT_END')