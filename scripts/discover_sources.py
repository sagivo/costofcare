#!/usr/bin/env python3
"""Discover primary MRF URLs using publicly linked hospital directory pages.
The directory is a locator only. Prices are always parsed from hospital files.
"""
import json,urllib.request,re,html,os,time
from concurrent.futures import ThreadPoolExecutor
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE='https://oria-data.trillianthealth.com'
def fetch(url):
 req=urllib.request.Request(url,headers={'User-Agent':'CostOfCare source discovery/1.0'})
 with urllib.request.urlopen(req,timeout=30) as r:return r.read().decode('utf-8','replace')
def main():
 registry=json.load(open(ROOT+'/data/registry.json')); existing=set(registry.get('directory_ids_checked',[])) | {r.get('directory_id') for r in registry['records']}
 index=json.loads(fetch(BASE+'/search-index.json'))
 candidates=[r for r in index if r['id'] not in existing]
 # Incremental locator crawl. Never count discovered locations as parsed coverage.
 def one(r):
  try:
   page=fetch(BASE+'/hospital/'+r['id'])
   links=[html.unescape(x) for x in re.findall(r'href="([^"]+)"',page)]
   urls=[u for u in links if u.startswith('http') and re.search(r'standardcharges|standard.charges',u,re.I)]
   if not urls:return None
   return {'id':'oria-'+r['id'],'directory_id':r['id'],'location_name':r['locationName'].strip(),'mrf_url':urls[0],'source_page_url':next((u for u in links if u.startswith('http') and re.search('transparency|pricing',u,re.I)),urls[0]),'discovery_url':BASE+'/hospital/'+r['id'],'city':r.get('city'),'state':r.get('state')}
  except Exception:return None
 with ThreadPoolExecutor(max_workers=3) as ex:
  for r in ex.map(one,candidates[:150]):
   if r:registry['records'].append(r)
 registry['directory_ids_checked']=sorted(str(x) for x in existing | {r['id'] for r in candidates[:150]} if x);registry['discovery_index_count']=len(index);registry['discovery_checked_at']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
 json.dump(registry,open(ROOT+'/data/registry.json','w'))
 print('registry',len(registry['records']),'discovery index',len(index))
if __name__=='__main__':main()
