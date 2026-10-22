#!/usr/bin/env python3
"""Build versioned, downloadable search data from our primary-source extractions."""
import json,glob,os,datetime
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def build():
 targets=json.load(open(ROOT+'/scripts/target_codes.json'))['codes']; providers=[]; rows=[]; attempts=[]; seen=set()
 for p in sorted(glob.glob(ROOT+'/data/hospitals/*.json')):
  d=json.load(open(p)); attempts.append({k:d.get(k) for k in ['id','status','extracted_at','error','last_attempt','last_error']})
  if d.get('status')!='ok' or d.get('mrf_url') in seen: continue
  seen.add(d['mrf_url']); i=len(providers)
  providers.append({k:d.get(k) for k in ['id','display_name','city','state','hospital_address','mrf_url','source_page_url','last_updated_on','extracted_at']})
  for code,v in d.get('codes',{}).items():
   if not any(v.get(k) for k in ['cash_min','payers','neg_min']): continue
   rows.append(dict(provider=i,code=code,**v))
 out={'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'procedures':targets,'providers':providers,'rows':rows,'attempts':attempts,'registry_locations':len(json.load(open(ROOT+'/data/registry.json'))['records'])}
 os.makedirs(ROOT+'/public/data',exist_ok=True)
 json.dump(out,open(ROOT+'/public/data/dataset.json','w'),separators=(',',':'))
 summary={'providers':len(providers),'cities':len(set((p['city'],p['state']) for p in providers if p['city'])),'rows':len(rows),'procedures':len(targets),'generated_at':out['generated_at'],'registry_locations':out['registry_locations']}
 json.dump(summary,open(ROOT+'/src/data/summary.json','w'))
 print(summary)
if __name__=='__main__': build()
