#!/usr/bin/env python3
"""Bounded diagnostic evidence only. Never guess a replacement encoding."""
import glob,json,urllib.request,datetime,hashlib,os
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def main():
 failures=[json.load(open(p)) for p in sorted(glob.glob(ROOT+'/data/normalized-attempts/*.json'))]
 selected=[d for d in failures if d.get('status')=='failed' and 'UnicodeDecodeError' in d.get('error','') and d['source_url'].lower().endswith('.csv')][:6]
 results=[]
 holds={x['hostname'] for x in json.load(open(ROOT+'/data/source-holds.json'))['holds']}
 for d in selected:
  if urllib.parse.urlsplit(d['source_url']).hostname in holds:continue
  item={'source_url':d['source_url'],'id':d['id']}
  try:
   req=urllib.request.Request(d['source_url'],headers={'Range':'bytes=0-65535','User-Agent':'CostOfCare encoding diagnostic/1.0'})
   with urllib.request.urlopen(req,timeout=30) as r:
    raw=r.read(65536);item.update(http_status=r.status,content_type=r.headers.get('Content-Type'),declared_charset=r.headers.get_content_charset(),sample_bytes=len(raw),sample_sha256=hashlib.sha256(raw).hexdigest())
   item['bom']=next((n for n,b in [('utf-32-le',b'\xff\xfe\x00\x00'),('utf-32-be',b'\x00\x00\xfe\xff'),('utf-16-le',b'\xff\xfe'),('utf-16-be',b'\xfe\xff'),('utf-8',b'\xef\xbb\xbf')] if raw.startswith(b)),None)
   try:raw.decode('utf-8-sig');item['sample_strict_utf8']='pass'
   except UnicodeDecodeError as e:item.update(sample_strict_utf8='fail',first_invalid_offset=e.start,first_invalid_byte=raw[e.start])
   item['disposition']='held: no fallback encoding authorized by this diagnostic'
  except Exception as e:item.update(error=str(e)[:300])
  results.append(item)
 report={'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'First 64KiB of first six sorted direct-CSV encoding failures (compressed sources excluded); HTTP encoding declaration and BOM evidence only. A valid prefix does not validate the full source. No conversion performed.','results':results}
 json.dump(report,open(ROOT+'/data/quality/encoding-diagnostics.json','w'),indent=2)
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
