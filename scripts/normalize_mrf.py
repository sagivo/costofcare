#!/usr/bin/env python3
"""Row-preserving primary MRF extraction. Never collapse setting, class or plan.

Output records retain original source fields, source-file SHA256 and source-row
ordinal. Target code filtering is explicit in the manifest; this is not a full-file
copy or independent validation of published amounts. Supports CMS JSON and CSV
through the same bounded download/unwrapping primitives as the summary parser.

Parser 1.3 remediation rules (each is recorded, none silent):
- Encoding: strict UTF-8 first. If a source is not valid UTF-8, a full strict
  Windows-1252 decode is attempted; success is recorded as an INFERRED encoding on
  the manifest and every record. UTF-16 only on an explicit BOM. Otherwise fail.
- CSV rows whose cell count differs from the header are preserved verbatim and
  flagged row_width_mismatch. Their cells are never realigned or padded, and
  their code match is flagged as alignment-unverified.
- A UTF-8 BOM before JSON no longer misroutes the file to the CSV parser.
"""
import argparse,csv,gzip,hashlib,io,json,os,re,time,tempfile
import mrf_extract as m
import ijson

PARSER_VERSION='row-preserving-1.3'
LEADING_SKIP=set(b' \t\r\n\x0b\x0c\xef\xbb\xbf')

def detect_bom(path):
 payload=m.open_payload(path)
 try:head=payload.read(4)
 finally:payload.close()
 if head[:4] in (b'\xff\xfe\x00\x00',b'\x00\x00\xfe\xff'):return 'utf-32'
 if head[:2] in (b'\xff\xfe',b'\xfe\xff'):return 'utf-16'
 return None

def extract(path,targets,encoding='utf-8-sig'):
 payload=m.open_payload(path)
 if encoding.startswith('utf-16') or encoding.startswith('utf-32'):
  b=b'x'  # BOM-declared wide encoding: CSV only
  chain=payload
 else:
  b=payload.read(1)
  while b and b[0] in LEADING_SKIP:b=payload.read(1)
  chain=m.ChainReader(b,payload)
 text=io.TextIOWrapper(io.BufferedReader(chain),encoding=encoding,errors='strict',newline='')
 try:
  if b==b'{':
   for ordinal,item in enumerate(ijson.items(text,'standard_charge_information.item',use_float=True),1):
    matched=[str(c.get('code')) for c in item.get('code_information',[]) if str(c.get('code')) in targets and m.CPT_TYPE_RE.match(str(c.get('type','')).strip())]
    if matched:yield {'source_record_ordinal':ordinal,'code_matches':matched,'source_format':'cms-json','source_fields':item}
  else:
   reader,header,meta=m.sniff_csv(text,targets,preserve_headers=True)
   duplicates=len(set(header))!=len(header)
   lookup=[h.strip().lower() for h in header]
   for ordinal,row in enumerate(reader,1):
    matched=[]
    for i,key in enumerate(lookup):
     if re.fullmatch(r'code\|\d+',key) and i<len(row) and row[i].strip() in targets:
      typekey=key+'|type';typ=row[lookup.index(typekey)] if typekey in lookup and lookup.index(typekey)<len(row) else ''
      if m.CPT_TYPE_RE.match(typ.strip()):matched.append(row[i].strip())
    if matched:
     rec={'source_record_ordinal':ordinal,'code_matches':sorted(set(matched)),'source_format':'cms-csv','source_header':header,'source_values':row,'duplicate_header_names':duplicates,'metadata':meta}
     if len(row)!=len(header):
      rec['row_width_mismatch']={'header_cells':len(header),'row_cells':len(row),'note':'cells preserved verbatim; no realignment or padding; code match alignment unverified'}
     yield rec
 finally:
  text.close()
  payload.close()

def write_rows(path,targets,dest,encoding,url,sha,sid,inferred):
 n=0;mismatched=0
 with gzip.GzipFile(filename=dest+'.tmp',mode='wb',mtime=0) as f:
  for row in extract(path,targets,encoding):
   row.update(source_url=url,source_sha256=sha,source_id=sid)
   if inferred:row['source_encoding_inferred']=encoding
   mismatched+='row_width_mismatch' in row
   f.write((json.dumps(row,separators=(',',':'))+'\n').encode());n+=1
   if n%100==0 and f.fileobj.tell()>18_000_000:raise ValueError('normalized output exceeds repository file budget; shard before publishing')
 return n,mismatched

def main():
 p=argparse.ArgumentParser();p.add_argument('--url',required=True);p.add_argument('--id',required=True);p.add_argument('--out-dir',default='data/normalized');p.add_argument('--max-mb',type=int,default=700);a=p.parse_args()
 targets,_=m.load_codes(m.DEFAULT_CODES);os.makedirs(a.out_dir,exist_ok=True)
 path,total=m.download(a.url,a.max_mb*1024*1024)
 digest=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):digest.update(b)
 sha=digest.hexdigest()
 dest=a.out_dir+'/'+a.id+'.jsonl.gz'
 try:
  wide=detect_bom(path);encoding='utf-8-sig';inferred=False;strict_utf8_error=None
  if wide:encoding=wide;inferred=False
  try:n,mismatched=write_rows(path,targets,dest,encoding,a.url,sha,a.id,False)
  except UnicodeDecodeError as e:
   if wide:raise
   strict_utf8_error='%s at byte %s'%(e.reason,e.start)
   encoding='cp1252';inferred=True
   n,mismatched=write_rows(path,targets,dest,encoding,a.url,sha,a.id,True)
  os.replace(dest+'.tmp',dest)
  manifest={'parser_version':PARSER_VERSION,'schema_version':'1.0.0','records':n,'source_url':a.url,'source_sha256':sha,'download_bytes':total,'extracted_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'code_filter':sorted(targets),'complete_source_download':True,'complete_target_code_scan':True,'source_truth_independently_verified':False,'source_encoding':encoding,'source_encoding_inferred':inferred,'strict_utf8_failure':strict_utf8_error,'row_width_mismatch_records':mismatched,'preserves':'raw source fields, original payer and plan strings, modifiers, setting, billing class, methodology and source ordinal'}
  json.dump(manifest,open(dest+'.manifest.json','w'),indent=2);print(json.dumps(manifest))
 finally:
  os.unlink(path)
  if os.path.exists(dest+'.tmp'):os.unlink(dest+'.tmp')
if __name__=='__main__':main()
