#!/usr/bin/env python3
"""Independent CSV readback of a bounded, deterministic sample.

Downloads original small uncompressed CSVs; uses stdlib CSV record parsing rather
than the normalized extractor; compares full header/value arrays at source ordinal.
A matching file hash proves repeatability of a snapshot, not hospital correctness.
"""
import csv,gzip,glob,hashlib,io,json,os,datetime,urllib.request
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def main():
 candidates=[]
 for p in glob.glob(ROOT+'/data/normalized/*.manifest.json'):
  m=json.load(open(p))
  if m.get('download_bytes',10**12)>3_000_000 or not m['source_url'].lower().endswith('.csv'):continue
  candidates.append((m['download_bytes'],p,m))
 results=[]
 for _,p,m in sorted(candidates)[:5]:
  result={'source_url':m['source_url'],'snapshot_sha256':m['source_sha256']}
  try:
   with urllib.request.urlopen(urllib.request.Request(m['source_url'],headers={'User-Agent':'CostOfCare source readback/1.0'}),timeout=30) as r:raw=r.read(3_000_001)
   if len(raw)>3_000_000:raise ValueError('bounded readback download cap')
   sha=hashlib.sha256(raw).hexdigest();result['readback_sha256']=sha
   if sha!=m['source_sha256']:
    result['status']='source_changed_since_snapshot';results.append(result);continue
   with gzip.open(p.removesuffix('.manifest.json'),'rt') as f:sample=[json.loads(l) for _,l in zip(range(3),f)]
   reader=csv.reader(io.StringIO(raw.decode('utf-8-sig')));header=None
   for row in reader:
    if 'description' in row and any(x.startswith('code|') for x in row):header=row;break
   if header is None:raise ValueError('independent header not found')
   wanted={r['source_record_ordinal']:r for r in sample};compared=0
   for ordinal,row in enumerate(reader,1):
    if ordinal not in wanted:continue
    original=wanted[ordinal]
    if header!=original['source_header'] or row!=original['source_values']:raise ValueError('full row/header mismatch at '+str(ordinal))
    compared+=1
    if compared==len(wanted):break
   if compared!=len(wanted):raise ValueError('sample ordinal missing')
   result.update(status='exact_source_readback_match',records_compared=compared)
  except Exception as e:result.update(status='failed',error=str(e)[:300])
  results.append(result)
 report={'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sampling':'five smallest eligible direct CSV sources <=3MB; first three matching source records each; not random or representative','scope':'independent full original CSV header/value readback and source hash; not clinical equivalence, provider attribution or source truth certification','results':results}
 json.dump(report,open(ROOT+'/data/quality/source-readback.json','w'),indent=2);print([(x['status'],x.get('records_compared')) for x in results])
if __name__=='__main__':main()
