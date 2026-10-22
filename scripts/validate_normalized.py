#!/usr/bin/env python3
"""Audit normalized artifacts: contract, counts, source attribution and exact identity.
Does not certify that the hospital's own amounts are clinically correct.
"""
import gzip,json,glob,os,collections,hashlib,sys,datetime
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def main():
 errors=[];sources=[];fields=collections.Counter();formats=collections.Counter();total=0
 for path in sorted(glob.glob(ROOT+'/data/normalized/*.jsonl.gz')):
  m=json.load(open(path+'.manifest.json'));n=0;seen=set();ordinals=set()
  try:
   with gzip.open(path,'rt',encoding='utf-8') as f:
    for line in f:
     r=json.loads(line);n+=1;total+=1;formats[r.get('source_format')]+=1
     if not r.get('source_url') or not r.get('source_id') or not r.get('code_matches'):raise ValueError('missing attribution or code')
     if r.get('source_sha256')!=m['source_sha256']:raise ValueError('source hash mismatch')
     ordinal=r.get('source_record_ordinal')
     if not isinstance(ordinal,int) or ordinal<1 or ordinal in ordinals:raise ValueError('invalid/repeated source ordinal')
     ordinals.add(ordinal)
     if r['source_format']=='cms-csv':
      header,values=r['source_header'],r['source_values']
      if len(header)!=len(values):raise ValueError('CSV alignment mismatch')
      for key,value in zip(header,values):
       if value.strip():fields[key]+=1
     else:
      for key in r.get('source_fields',{}):fields[key]+=1
     stable=hashlib.sha256(json.dumps(r,sort_keys=True,separators=(',',':')).encode()).hexdigest()
     if stable in seen:raise ValueError('duplicate exact record')
     seen.add(stable)
   if n!=m['records']:raise ValueError('manifest count mismatch')
   if not m.get('complete_source_download') or not m.get('complete_target_code_scan'):raise ValueError('incomplete scan')
   sources.append({'source_id':r.get('source_id') if n else os.path.basename(path),'records':n,'source_sha256':m['source_sha256'],'source_url':m['source_url'],'extracted_at':m['extracted_at']})
  except Exception as e:errors.append({'path':os.path.basename(path),'error':str(e)})
 out={'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'pass' if not errors else 'fail','validated_files':len(sources),'validated_records':total,'source_formats':dict(formats),'populated_field_counts':dict(fields),'sources':sources,'errors':errors,'scope':'Artifact integrity and source-preserving contract only; no independent clinical, coding, payer/network or amount validation'}
 os.makedirs(ROOT+'/data/quality',exist_ok=True);json.dump(out,open(ROOT+'/data/quality/normalized-validation.json','w'),indent=2)
 print(out['status'],len(sources),'files',total,'records',len(errors),'errors');return bool(errors)
if __name__=='__main__':sys.exit(main())
