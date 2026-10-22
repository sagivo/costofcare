#!/usr/bin/env python3
"""Bounded row-preserving rebuild from verified successful primary sources.

Run a small explicit tranche. Existing normalized manifests drive oldest-first
ordering; failures are separate from last-good data. Every output is code-filtered,
never counted as full-file all-service coverage. Hard caps are audited.
"""
import argparse,datetime,glob,json,os,subprocess,sys,tempfile,time,urllib.parse
from concurrent.futures import ThreadPoolExecutor,as_completed
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def main():
 p=argparse.ArgumentParser();p.add_argument('--limit',type=int,default=40);p.add_argument('--workers',type=int,default=3);p.add_argument('--max-mb',type=int,default=700);a=p.parse_args()
 holds={r['hostname'] for r in json.load(open(ROOT+'/data/source-holds.json'))['holds']}
 candidates=[];seen=set()
 for f in glob.glob(ROOT+'/data/hospitals/*.json'):
  d=json.load(open(f));u=d.get('mrf_url')
  if d.get('status')!='ok' or u in seen or urllib.parse.urlsplit(u or '').hostname in holds:continue
  seen.add(u);candidates.append(d)
 directory=ROOT+'/data/normalized';os.makedirs(directory,exist_ok=True)
 def age(d):
  path=directory+'/'+d['id']+'.jsonl.gz.manifest.json'
  if os.path.exists(path): return json.load(open(path)).get('extracted_at','')
  attempt=ROOT+'/data/normalized-attempts/'+d['id']+'.json'
  return json.load(open(attempt)).get('checked_at','') if os.path.exists(attempt) else ''
 candidates.sort(key=lambda d:(age(d),d.get('bytes',10**12),d['id']))
 selected=candidates[:a.limit] if a.limit else candidates
 def process(d):
  t=time.time();hid=d['id'];result={'id':hid,'source_url':d['mrf_url'],'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
  try:
   with tempfile.TemporaryDirectory() as temp:
    run=subprocess.run([sys.executable,ROOT+'/scripts/normalize_mrf.py','--id',hid,'--url',d['mrf_url'],'--out-dir',temp,'--max-mb',str(a.max_mb)],capture_output=True,text=True,timeout=240,env=dict(os.environ,TMPDIR=temp))
    if run.returncode:raise ValueError(run.stderr[-700:])
    manifest_path=temp+'/'+hid+'.jsonl.gz.manifest.json';manifest=json.load(open(manifest_path))
    # Install only complete verified-format output, then a manifest. Retain source history hash.
    for path in glob.glob(temp+'/*.jsonl.gz*'):os.replace(path,directory+'/'+os.path.basename(path))
    result.update(status='ok',records=manifest['records'],source_sha256=manifest['source_sha256'])
  except Exception as e:result.update(status='failed',error=str(e)[:800],previous_snapshot_preserved=True)
  result['seconds']=round(time.time()-t,1)
  os.makedirs(ROOT+'/data/normalized-attempts',exist_ok=True);json.dump(result,open(ROOT+'/data/normalized-attempts/'+hid+'.json','w'))
  print(hid,result['status'],result.get('records'),flush=True)
 with ThreadPoolExecutor(max_workers=a.workers) as ex:list(ex.map(process,selected))
if __name__=='__main__':main()
