#!/usr/bin/env python3
"""Independent CSV readback of a bounded, deterministic sample.

Downloads original small uncompressed CSVs; uses stdlib CSV record parsing rather
than the normalized extractor; compares full header/value arrays at source ordinal.
A matching file hash proves repeatability of a snapshot, not hospital correctness.
"""
import csv,gzip,glob,hashlib,io,json,os,datetime,urllib.request,urllib.parse
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def main():
 candidates=[]
 holds={x['hostname'] for x in json.load(open(ROOT+'/data/source-holds.json'))['holds']}
 for p in glob.glob(ROOT+'/data/normalized/*.manifest.json'):
  m=json.load(open(p))
  if m.get('download_bytes',10**12)>3_000_000 or not m['source_url'].lower().endswith('.csv'):continue
  if urllib.parse.urlsplit(m['source_url']).hostname in holds:continue
  candidates.append((hashlib.sha256(m['source_url'].encode()).hexdigest(),p,m))
 results=[];seen_hosts=set()
 for _,p,m in sorted(candidates):
  host=urllib.parse.urlsplit(m['source_url']).hostname
  if host in seen_hosts:continue
  seen_hosts.add(host)
  if len(results)>=12:break
  result={'source_url':m['source_url'],'snapshot_sha256':m['source_sha256']}
  try:
   with urllib.request.urlopen(urllib.request.Request(m['source_url'],headers={'User-Agent':'CostOfCare source readback/1.0'}),timeout=30) as r:raw=r.read(3_000_001)
   if len(raw)>3_000_000:raise ValueError('bounded readback download cap')
   sha=hashlib.sha256(raw).hexdigest();result['readback_sha256']=sha
   if sha!=m['source_sha256']:
    result['status']='source_changed_since_snapshot';results.append(result);continue
   with gzip.open(p.removesuffix('.manifest.json'),'rt') as f:rows=[json.loads(l) for l in f]
   sample=[rows[i] for i in sorted({0,len(rows)//2,len(rows)-1})] if rows else []
   if not sample:raise ValueError('no normalized rows to compare')
   reader=csv.reader(io.StringIO(raw.decode('utf-8-sig')));header=None
   for row in reader:
    if 'description' in row and any(x.startswith('code|') for x in row):header=row;break
   if header is None:raise ValueError('independent header not found')
   wanted={r['source_record_ordinal']:r for r in sample};compared=0;header_trimmed=False
   for ordinal,row in enumerate(reader,1):
    if ordinal not in wanted:continue
    original=wanted[ordinal]
    if row!=original['source_values']:raise ValueError('source value mismatch at '+str(ordinal))
    if header!=original['source_header']:
     if [h.strip() for h in header]!=original['source_header']:raise ValueError('header mismatch beyond whitespace at '+str(ordinal))
     header_trimmed=True
    compared+=1
    if compared==len(wanted):break
   if compared!=len(wanted):raise ValueError('sample ordinal missing')
   result.update(status=('source_values_match_header_whitespace_trimmed' if header_trimmed else 'exact_source_readback_match'),records_compared=compared)
  except Exception as e:result.update(status='failed',error=str(e)[:300])
  results.append(result)
 report={'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sampling':'up to twelve distinct-host direct CSV sources <=3MB, deterministic URL-hash ordering; first/middle/last preserved record per file; excludes source holds; not random or representative','scope':'independent full original CSV header/value readback and source hash; not clinical equivalence, provider attribution or source truth certification','results':results}
 json.dump(report,open(ROOT+'/data/quality/source-readback.json','w'),indent=2);print([(x['status'],x.get('records_compared')) for x in results])
if __name__=='__main__':main()
