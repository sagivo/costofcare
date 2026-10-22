#!/usr/bin/env python3
"""Refresh versioned public-source catalogs and compact reference datasets.

Catalog records are locators, NOT downloaded/parsed price coverage. Large source
files are deliberately not vendored wholesale. JSONL catalogs are split below
20 MB; no file is allowed to cross GitHub's per-file limit. Failed refreshes
preserve the previous snapshot and are recorded in status.json.
"""
import csv,gzip,hashlib,io,json,os,re,tempfile,time,urllib.request,datetime,html
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA=ROOT+'/data'; UA='CostOfCare public-data research/1.0'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def fetch(url,cap=100_000_000):
 req=urllib.request.Request(url,headers={'User-Agent':UA})
 with urllib.request.urlopen(req,timeout=90) as r:
  b=r.read(cap+1)
  if len(b)>cap:raise ValueError('source exceeds bounded catalog download cap')
  return b

def getjson(url):return json.loads(fetch(url))
def write_json(path,d):
 os.makedirs(os.path.dirname(path),exist_ok=True)
 t=path+'.tmp';json.dump(d,open(t,'w'),ensure_ascii=False,separators=(',',':'));os.replace(t,path)
def shards(name,records):
 directory=DATA+'/catalogs/'+name;os.makedirs(directory,exist_ok=True)
 # Write into a temporary directory first, preserving last good snapshot on failure.
 with tempfile.TemporaryDirectory() as tmp:
  paths=[];f=None;size=0;count=0
  for row in records:
   line=(json.dumps(row,separators=(',',':'),ensure_ascii=False)+'\n').encode()
   if f is None or size+len(line)>18_000_000:
    if f:f.close()
    p=f'{tmp}/part-{len(paths):04d}.jsonl.gz';f=gzip.GzipFile(filename=p,mode='wb',compresslevel=6,mtime=0);paths.append(p);size=0
   f.write(line);size+=len(line);count+=1
  if f:f.close()
  for p in paths:os.replace(p,directory+'/'+os.path.basename(p))
  keep={os.path.basename(p) for p in paths}
  for old in os.listdir(directory):
   if old.startswith('part-') and old not in keep:os.unlink(directory+'/'+old)
  manifest={'checked_at':now(),'records':count,'meaning':'source locators, not parsed price coverage','parts':[]}
  for filename in sorted(keep):
   b=open(directory+'/'+filename,'rb').read();manifest['parts'].append({'path':filename,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()})
  write_json(directory+'/manifest.json',manifest)
 return manifest

def cigna():
 discovery='https://www.cigna.com/static/mrf/latest.json';d=getjson(discovery)
 toc=d['mrfs'][0]['files'][0];index=getjson(toc['url']);last=index.get('last_updated_on')
 def rows():
  for group in index.get('reporting_structure',[]):
   plans=group.get('reporting_plans',[])
   for kind in ['in_network_files','allowed_amount_file','allowed_amount_files']:
    files=group.get(kind,[])
    if isinstance(files,dict):files=[files]
    for f in files:
     if f.get('location'):yield {'kind':kind,'location':f['location'],'description':f.get('description'),'reporting_plans':plans,'source_updated':last}
 m=shards('cigna-tic',rows());m.update(source_url=discovery,index_updated=last,reporting_structures=len(index.get('reporting_structure',[])));return m

def uhc():
 url='https://transparency-in-coverage.uhc.com/api/v1/uhc/blobs/';d=getjson(url)
 return dict(shards('uhc-tic',({'name':x['name'],'location':x['downloadUrl'],'bytes':x.get('size')} for x in d['blobs'])),source_url=url)

def oria():
 url='https://oria-data.trillianthealth.com/search-index.json';d=getjson(url)
 # Strip irrelevant contact email; retain directory IDs and geography only.
 return dict(shards('hospital-locator',({'id':r['id'],'location_name':r['locationName'],'hospital_name':r.get('hospitalName'),'city':r.get('city'),'state':r.get('state'),'directory_url':'https://oria-data.trillianthealth.com/hospital/'+r['id']} for r in d)),source_url=url)

def cms():
 url='https://data.cms.gov/data.json';d=getjson(url);selected=[]
 pattern=re.compile(r'hospital|physician|clinical laboratory|fee schedule|drug|durable medical|ambulance|medicare spending|payment',re.I)
 for r in d['dataset']:
  if not pattern.search(r.get('title','')):continue
  selected.append({k:r.get(k) for k in ['title','identifier','description','modified','license','landingPage','distribution','temporal']})
 m=shards('cms-price-and-payment',selected);m.update(source_url=url,all_catalog_datasets=len(d['dataset']))
 write_json(DATA+'/catalogs/cms-price-and-payment/latest-series.json',[max((r for r in selected if r['title'].startswith(prefix)),key=lambda r:r['title']) for prefix in ['Medicare Inpatient Hospitals - by Provider and Service','Medicare Outpatient Hospitals - by Provider and Service','Medicare Physician & Other Practitioners - by Provider and Service']])
 meta_url='https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items/xubh-q36u';meta=getjson(meta_url);u=meta['distribution'][0]['downloadURL'];raw=fetch(u);rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
 write_json(DATA+'/reference/cms-hospital-directory.json',{'source_url':u,'metadata_url':meta_url,'source_updated':meta['modified'],'checked_at':now(),'meaning':'hospital directory, not prices','rows':rows})
 m['hospital_directory_rows']=len(rows);return m

def nadac():
 year=datetime.datetime.now().year
 # Versioned dataset ID is a discovery seed; retain source date, never call acquisition cost a retail quote.
 meta_url='https://data.medicaid.gov/api/1/metastore/schemas/dataset/items/fbb83258-11c7-47f5-8b18-5f8e79f7e704';meta=getjson(meta_url);url=meta['distribution'][0]['downloadURL']
 latest={};total=0
 with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':UA}),timeout=90) as response:
  for row in csv.DictReader(io.TextIOWrapper(response,encoding='utf-8-sig')):
   total+=1;ndc=row.get('NDC') or row.get('ndc')
   if not ndc:continue
   date=row.get('As of Date') or row.get('as_of_date') or row.get('Effective Date') or ''
   try:key=datetime.datetime.strptime(date,'%m/%d/%Y').date().isoformat()
   except ValueError:key=date
   previous=latest.get(ndc)
   if not previous or key>=previous[0]:latest[ndc]=(key,row)
 m=shards('nadac-latest-per-ndc',(r[1] for _,r in sorted(latest.items())));m.update(source_url=url,metadata_url=meta_url,source_updated=meta['modified'],source_rows=total,meaning='pharmacy acquisition-cost benchmark, not patient retail price or local quote',license=meta.get('license'));return m

def medicare_payments():
 series=json.load(open(DATA+'/catalogs/cms-price-and-payment/latest-series.json'))
 results=[]
 for r in series[:2]:
  distribution=next(d for d in r['distribution'] if d.get('format','').upper()=='CSV' and d.get('downloadURL'))
  url=distribution['downloadURL'];raw=fetch(url,250_000_000)
  name='medicare-inpatient-provider-service' if 'Inpatient' in r['title'] else 'medicare-outpatient-provider-service'
  rows=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
  m=shards(name,rows);m.update(source_url=url,title=r['title'],source_updated=r.get('modified'),meaning='historical Medicare claims/payment aggregates, not current cash prices or commercial negotiated rates')
  write_json(DATA+'/catalogs/'+name+'/provenance.json',m);results.append(m)
 return {'datasets':results,'records':sum(r['records'] for r in results)}

def landing_pages():
 entries=[('Aetna','https://www.aetna.com/health-care-professionals/transparency-in-coverage.html'),('Humana','https://developers.humana.com/cost-transparency'),('Anthem','https://www.anthem.com/machine-readable-file/search/'),('Cigna','https://www.cigna.com/legal/compliance/machine-readable-files'),('UnitedHealthcare','https://transparency-in-coverage.uhc.com/')]
 rows=[]
 for name,url in entries:
  try:b=fetch(url);rows.append({'name':name,'source_url':url,'checked_at':now(),'status':'page_retrieved','sha256':hashlib.sha256(b).hexdigest(),'price_ingestion':'not implied by landing-page retrieval'})
  except Exception as e:rows.append({'name':name,'source_url':url,'checked_at':now(),'status':'failed','error':str(e)[:250]})
 write_json(DATA+'/catalogs/insurer-landing-pages.json',rows);return {'entries':len(rows)}

def main():
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--only',default='oria,cigna,uhc,cms,nadac,medicare_payments,landing_pages');args=p.parse_args()
 status_path=DATA+'/catalogs/status.json';status=json.load(open(status_path)) if os.path.exists(status_path) else {}
 for name in args.only.split(','):
  try:result=globals()[name]();status[name]={'status':'ok','checked_at':now(),**result};print(name,'ok',result.get('records',result.get('entries')),flush=True)
  except Exception as e:status[name]={'status':'failed','checked_at':now(),'error':str(e)[:350],'previous_snapshot_preserved':True};print(name,'failed',str(e)[:150],flush=True)
  write_json(status_path,status)
if __name__=='__main__':main()
