#!/usr/bin/env python3
"""Row-preserving primary MRF extraction. Never collapse setting, class or plan.

Output records retain original source fields, source-file SHA256 and source-row
ordinal. Target code filtering is explicit in the manifest; this is not a full-file
copy or independent validation of published amounts. Supports CMS JSON and CSV
through the same bounded download/unwrapping primitives as the summary parser.
"""
import argparse,csv,gzip,hashlib,io,json,os,re,time,tempfile
import mrf_extract as m
import ijson

def extract(path,targets):
 payload=m.open_payload(path);b=payload.read(1)
 while b and b.isspace():b=payload.read(1)
 text=io.TextIOWrapper(io.BufferedReader(m.ChainReader(b,payload)),encoding='utf-8-sig',errors='strict',newline='')
 try:
  if b==b'{':
   for ordinal,item in enumerate(ijson.items(text,'standard_charge_information.item',use_float=True),1):
    matched=[str(c.get('code')) for c in item.get('code_information',[]) if str(c.get('code')) in targets and m.CPT_TYPE_RE.match(str(c.get('type','')).strip())]
    if matched:yield {'source_record_ordinal':ordinal,'code_matches':matched,'source_format':'cms-json','source_fields':item}
  else:
   reader,header,meta=m.sniff_csv(text,targets,preserve_headers=True)
   if len(set(header))!=len(header):
    # Empty padding headers are common; preserve the entire aligned array rather than silently dropping duplicates.
    duplicates=True
   else:duplicates=False
   lookup=[h.strip().lower() for h in header]
   for ordinal,row in enumerate(reader,1):
    matched=[]
    for i,key in enumerate(lookup):
     if re.fullmatch(r'code\|\d+',key) and i<len(row) and row[i].strip() in targets:
      typekey=key+'|type';typ=row[lookup.index(typekey)] if typekey in lookup and lookup.index(typekey)<len(row) else ''
      if m.CPT_TYPE_RE.match(typ.strip()):matched.append(row[i].strip())
    if matched:
     if len(row)!=len(header):raise ValueError('CSV row width mismatch at ordinal '+str(ordinal))
     yield {'source_record_ordinal':ordinal,'code_matches':sorted(set(matched)),'source_format':'cms-csv','source_header':header,'source_values':row,'duplicate_header_names':duplicates,'metadata':meta}
 finally:
  text.close()
  payload.close()

def main():
 p=argparse.ArgumentParser();p.add_argument('--url',required=True);p.add_argument('--id',required=True);p.add_argument('--out-dir',default='data/normalized');p.add_argument('--max-mb',type=int,default=700);a=p.parse_args()
 targets,_=m.load_codes(m.DEFAULT_CODES);os.makedirs(a.out_dir,exist_ok=True)
 path,total=m.download(a.url,a.max_mb*1024*1024)
 digest=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):digest.update(b)
 sha=digest.hexdigest();n=0;checks=0
 dest=a.out_dir+'/'+a.id+'.jsonl.gz'
 try:
  with gzip.GzipFile(filename=dest+'.tmp',mode='wb',mtime=0) as f:
   for row in extract(path,targets):
    row.update(source_url=a.url,source_sha256=sha,source_id=a.id)
    f.write((json.dumps(row,separators=(',',':'))+'\n').encode());n+=1
    if n%100==0 and f.fileobj.tell()>18_000_000:raise ValueError('normalized output exceeds repository file budget; shard before publishing')
  os.replace(dest+'.tmp',dest)
  manifest={'parser_version':'row-preserving-1.2','schema_version':'1.0.0','records':n,'source_url':a.url,'source_sha256':sha,'download_bytes':total,'extracted_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'code_filter':sorted(targets),'complete_source_download':True,'complete_target_code_scan':True,'source_truth_independently_verified':False,'preserves':'raw source fields, original payer and plan strings, modifiers, setting, billing class, methodology and source ordinal'}
  json.dump(manifest,open(dest+'.manifest.json','w'),indent=2);print(json.dumps(manifest))
 finally:
  os.unlink(path)
  if os.path.exists(dest+'.tmp'):os.unlink(dest+'.tmp')
if __name__=='__main__':main()
