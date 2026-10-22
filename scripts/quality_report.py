#!/usr/bin/env python3
"""Publish measured coverage and QA flags without claiming ground-truth accuracy."""
import json,glob,datetime,os,collections,math,sys
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
now=datetime.datetime.now(datetime.timezone.utc)
def parse_date(v):
 for fmt in ['%Y-%m-%d','%m/%d/%Y']:
  try:return datetime.datetime.strptime(str(v).strip(),fmt).date()
  except (ValueError,TypeError):pass
 return None

def main():
 files=[json.load(open(p)) for p in glob.glob(ROOT+'/data/hospitals/*.json')]
 flags=[];codes=collections.Counter();states=collections.Counter();statuses=collections.Counter();distinct=set();good=0;fresh24=0;oldsource=0;missingdate=0;detail=0
 for d in files:
  hid=d.get('id');statuses[d.get('status','unknown')]+=1
  if d.get('status')!='ok':continue
  good+=1;distinct.add(d.get('mrf_url'));states[d.get('state') or 'unresolved']+=1
  if not d.get('city') or not d.get('state'):flags.append({'id':hid,'flag':'unresolved_geography'})
  if not d.get('source_sha256'):flags.append({'id':hid,'flag':'source_bytes_hash_missing'})
  dt=parse_date(d.get('last_updated_on'))
  if dt is None:missingdate+=1;flags.append({'id':hid,'flag':'source_update_date_unparseable','value':d.get('last_updated_on')})
  elif dt>now.date():flags.append({'id':hid,'flag':'future_source_update_date','value':str(dt)})
  elif (now.date()-dt).days>365:oldsource+=1;flags.append({'id':hid,'flag':'source_over_365_days_old','age_days':(now.date()-dt).days})
  try:
   extracted=datetime.datetime.fromisoformat(d['extracted_at'].replace('Z','+00:00'));fresh24+=(now-extracted).total_seconds()<86400
  except Exception:flags.append({'id':hid,'flag':'extraction_time_unparseable'})
  for c,r in d.get('codes',{}).items():
   codes[c]+=1
   # Aggregated ranges are prototype views, not comparable all-in offers.
   for low,high in [('cash_min','cash_max'),('gross_min','gross_max'),('neg_min','neg_max')]:
    l,h=r.get(low),r.get(high)
    if l is not None and (not isinstance(l,(int,float)) or not math.isfinite(l) or l<0):flags.append({'id':hid,'code':c,'flag':'invalid_numeric','field':low})
    if l is not None and h is not None and l>h:flags.append({'id':hid,'code':c,'flag':'range_inverted','field':low})
   for payer,p in r.get('payers',{}).items():
    if p.get('low',0)>p.get('high',0):flags.append({'id':hid,'code':c,'payer':payer,'flag':'payer_range_inverted'})
    elif p.get('low',0)>0 and p.get('high',0)/p['low']>100:flags.append({'id':hid,'code':c,'payer':payer,'flag':'wide_payer_range_review','ratio':round(p['high']/p['low'],2)})
 for p in glob.glob(ROOT+'/data/normalized/*.manifest.json'):
  d=json.load(open(p));detail+=d.get('records',0)
 report={'generated_at':now.isoformat(),'definition':'Measured pipeline coverage and structural QA, NOT independently verified price accuracy','counts':{'attempted_registry_entries':len(files),'successful_entries':good,'distinct_successful_mrf_urls':len(distinct),'extracted_within_24h':fresh24,'sources_over_365_days_old':oldsource,'source_date_unparseable':missingdate,'hospital_code_aggregates':sum(codes.values()),'row_preserving_records':detail},'status_counts':dict(statuses),'successful_entries_by_state':dict(states),'hospital_entries_per_code':dict(codes),'qa_flags':flags,'limitations':['Primary summaries collapse settings, billing classes, modifiers and plans. Do not rank them as equivalent treatment bundles.','Raw payer strings and plan identity are lost in legacy summary layer. New normalized records preserve them.','A parser success is not confirmation that a hospital published correct prices.','Insurer catalogs and CMS benchmarks are separate layers and do not increase primary local price coverage.','No claim of best-in-world accuracy, completeness or freshness is supported.']}
 os.makedirs(ROOT+'/data/quality',exist_ok=True);json.dump(report,open(ROOT+'/data/quality/report.json','w'),indent=2)
 print(json.dumps(report['counts']));print('QA flags',len(flags))
 if any(f['flag'] in ['invalid_numeric','range_inverted','payer_range_inverted'] for f in flags):return 1
 return 0
if __name__=='__main__':sys.exit(main())
