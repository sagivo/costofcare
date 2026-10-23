#!/usr/bin/env python3
"""Resolve npi-type TINs captured in TiC manifests against the public NPPES
registry API. Stores registry facts per NPI in data/tic-providers/ with the
lookup date. No name/address matching to hospitals is performed here: this is
authoritative registry data per NPI, not a verified join to hospital identity.
EIN-type TINs have no authoritative public registry and stay unresolved.
Rate-polite: one request per second, bounded cap per run.
"""
import argparse,glob,json,os,time,urllib.request,urllib.parse

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API='https://npiregistry.cms.hhs.gov/api/'

def collect_npis():
    npis=set();eins=set()
    for p in glob.glob(os.path.join(ROOT,'data','tic','*.manifest.json')):
        m=json.load(open(p))
        for ref in m.get('provider_references',[]):
            for t in ref.get('tins',[]):
                v=str(t.get('value') or '')
                if t.get('type')=='npi' and v.isdigit() and len(v)==10:npis.add(v)
                elif v:eins.add(v)
    return sorted(npis),sorted(eins)

def lookup(npi):
    url=API+'?'+urllib.parse.urlencode({'version':'2.1','number':npi})
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'CostOfCare research/1.0'}),timeout=30) as r:
        return json.load(r)

def slim(res):
    out=[]
    for r in res.get('results',[]):
        b=r.get('basic',{})
        loc=[a for a in r.get('addresses',[]) if a.get('address_purpose')=='LOCATION']
        out.append({'number':r.get('number'),'enumeration_type':r.get('enumeration_type'),
            'organization_name':b.get('organization_name'),
            'first_name':b.get('first_name'),'last_name':b.get('last_name'),
            'primary_taxonomy':next((t.get('desc') for t in r.get('taxonomies',[]) if t.get('primary')),None),
            'location':{k:loc[0].get(k) for k in ('address_1','city','state','postal_code')} if loc else None,
            'last_updated':b.get('last_updated')})
    return out

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--cap',type=int,default=100);a=ap.parse_args()
    npis,eins=collect_npis()
    odir=os.path.join(ROOT,'data','tic-providers');os.makedirs(odir,exist_ok=True)
    done={os.path.basename(p)[:-5] for p in glob.glob(os.path.join(odir,'*.json'))}
    todo=[n for n in npis if n not in done][:a.cap]
    for i,npi in enumerate(todo):
        rec={'npi':npi,'source':'NPPES public registry API v2.1','source_url':API,
             'looked_up_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
             'join_semantics':'registry facts for this NPI only; not a verified hospital-identity join'}
        try:
            res=lookup(npi);rec['result_count']=res.get('result_count',0);rec['results']=slim(res)
        except Exception as e:
            rec['error']=repr(e)[-300:]
        json.dump(rec,open(os.path.join(odir,npi+'.json'),'w'),indent=2)
        if i<len(todo)-1:time.sleep(1)
    idx={'generated_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
         'npi_type_tins_total':len(npis),'ein_type_tins_total':len(eins),
         'npi_lookups_stored':len(done)+len(todo),'ein_unresolved_reason':'no authoritative public EIN-to-provider registry',
         'caveat':'NPPES rows are registry self-reported facts per NPI, not verified network or hospital-identity joins.'}
    json.dump(idx,open(os.path.join(odir,'index.json'),'w'),indent=2)
    print('npis',len(npis),'eins',len(eins),'new lookups',len(todo))
if __name__=='__main__':main()
