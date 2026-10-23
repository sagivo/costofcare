#!/usr/bin/env python3
"""Join byte-level source lineage, freshness and failed-attempt evidence.

Does not certify provider identity, source accuracy or source update freshness.
"""
import collections,datetime,glob,json,os
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def main():
 now=datetime.datetime.now(datetime.timezone.utc);summary={};parsers=collections.Counter();ages=collections.Counter();failures=collections.Counter();different=[];unmatched=[];missing_hash=0
 for p in glob.glob(ROOT+'/data/hospitals/*.json'):
  d=json.load(open(p));u=d.get('mrf_url')
  if d.get('status')=='ok' and (u not in summary or d.get('extracted_at','')>summary[u].get('extracted_at','')):summary[u]=d
 manifests=[json.load(open(p)) for p in glob.glob(ROOT+'/data/normalized/*.manifest.json')]
 for m in manifests:
  parsers[m.get('parser_version','unversioned')]+=1
  try:
   stamp=datetime.datetime.fromisoformat(m['extracted_at'].replace('Z','+00:00'));hours=(now-stamp).total_seconds()/3600
   ages['future' if hours<0 else 'within_24h' if hours<24 else '1_to_7_days' if hours<168 else 'over_7_days']+=1
  except (KeyError,ValueError):ages['unparseable']+=1
  s=summary.get(m['source_url'])
  if s is None:unmatched.append(m['source_url']);continue
  if not s.get('source_sha256'):missing_hash+=1
  elif m['source_sha256']!=s['source_sha256']:different.append({'source_url':m['source_url'],'normalized_sha256':m['source_sha256'],'summary_sha256':s['source_sha256'],'normalized_extracted_at':m['extracted_at'],'summary_extracted_at':s['extracted_at']})
 for p in glob.glob(ROOT+'/data/normalized-attempts/*.json'):
  d=json.load(open(p))
  if d.get('status')!='failed':continue
  e=d.get('error','');kind='strict_encoding' if 'UnicodeDecodeError' in e else 'timeout' if 'timed out' in e else 'csv_width' if 'width mismatch' in e else 'http_429' if '429' in e else 'other'
  failures[kind]+=1
 report={'generated_at':now.isoformat(),'normalized_files':len(manifests),'parser_versions':dict(parsers),'extraction_age_buckets':dict(ages),'failed_attempt_classes':dict(failures),'summary_hash_missing_count':missing_hash,'summary_normalized_hash_differences':different,'normalized_without_successful_summary':unmatched,'refresh_policy':{'normalized_scheduled_max_files_per_day':240,'nominal_full_rotation_days_at_current_file_count':(len(manifests)+239)//240,'caveat':'Lower-bound rotation estimate only: failures, new sources, scheduling and manual tranches change cadence; this is not a freshness guarantee.'},'interpretation':'Matching hashes indicate the same downloaded bytes, not correct prices or clinical equivalence. Different hashes can reflect newer source versions or nondeterministic containers and require review. Age is extraction age, not hospital update age. Legacy parser 1.1 trims CSV header whitespace; 1.2 preserves exact headers.'}
 json.dump(report,open(ROOT+'/data/quality/lineage-freshness.json','w'),indent=2)
 print({k:v for k,v in report.items() if k not in ['summary_normalized_hash_differences','normalized_without_successful_summary']});print('hash differences',len(different),'unmatched',len(unmatched))
if __name__=='__main__':main()
