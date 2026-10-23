#!/usr/bin/env python3
"""Bounded tranche extraction of insurer TiC in-network files into data/tic/.

Separate layer from hospital MRF data: never combined into shared counts.
Only UHC-style single-file .json.gz URLs are handled here; zip archives
(most Cigna entries) are skipped and recorded, not interpreted.
Allowed-amounts files are excluded by design (different schema, not
in-network negotiated prices). Capitation and bundle rows are kept with
their negotiation_arrangement qualifier, never mixed into per-service prices.
Provider references are retained verbatim and remain unresolved until a
verified provider-directory join exists; patient_price_ready stays False.
"""
import argparse,gzip,hashlib,io,json,os,time,urllib.request,zipfile
import ijson

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA={'User-Agent':'CostOfCare TiC research/1.0'}

def key(url):return hashlib.sha256(url.encode()).hexdigest()[:16]

def load_codes():
    d=json.load(open(os.path.join(ROOT,'scripts','target_codes.json')))
    return set(d['codes'])

def candidates(max_bytes):
    import glob
    out=[]
    for p in sorted(glob.glob(os.path.join(ROOT,'data/catalogs/uhc-tic/part-*.jsonl.gz'))):
        with gzip.open(p,'rt') as f:
            for line in f:
                r=json.loads(line);n=r.get('name','')
                if 'in-network-rates' not in n:continue
                b=r.get('bytes',0)
                if b and b<=max_bytes:out.append((b,r['location'],n))
    out.sort()
    return out

def stream_for(raw,head):
    buffered=io.BufferedReader(raw)
    first=buffered.peek(4)[:4]
    if first[:2]==b'\x1f\x8b':return gzip.GzipFile(fileobj=buffered),'gzip'
    if first[:2]==b'PK':return None,'zip-skipped'
    return buffered,'plain'

def read_provider_refs(url,timeout,limit_groups=200):
    refs=[]
    req=urllib.request.Request(url,headers=UA)
    with urllib.request.urlopen(req,timeout=timeout) as raw:
        stream,enc=stream_for(raw,None)
        if stream is None:return refs,'zip-skipped'
        try:
            for ref in ijson.items(stream,'provider_references.item'):
                entry={}
                if ref.get('provider_reference') is not None:
                    entry['external_provider_reference_url']=ref.get('provider_reference')
                groups=ref.get('provider_groups') or []
                entry['provider_group_count']=len(groups)
                tins=[];npi_total=0
                for g in groups[:limit_groups]:
                    t=g.get('tin') or {}
                    tins.append({'type':t.get('type'),'value':t.get('value')})
                    npi_total+=len(g.get('npi') or [])
                entry['tins']=tins;entry['npi_count']=npi_total
                if len(groups)>limit_groups:entry['provider_groups_truncated']=True
                refs.append(entry)
        except ijson.JSONError:
            return refs,'parse-error'
    return refs,'ok'

def extract(stream,output,codes,max_rows):
    count=0;complete=True
    try:
        for item in ijson.items(stream,'in_network.item',use_float=True):
            code=str(item.get('billing_code',''))
            if codes and code not in codes:continue
            for rate in item.get('negotiated_rates',[]):
                for p in rate.get('negotiated_prices',[]):
                    if p.get('negotiated_rate') is None:continue
                    if p.get('negotiated_type') not in ('negotiated','fee schedule','derived'):continue
                    row={'billing_code':code,'billing_code_type':item.get('billing_code_type'),
                         'description':item.get('description'),
                         'negotiation_arrangement':item.get('negotiation_arrangement'),
                         'provider_references':rate.get('provider_references'),
                         'provider_groups':rate.get('provider_groups'),'price':p}
                    output.write(json.dumps(row,separators=(',',':'))+'\n');count+=1
                    if max_rows and count>=max_rows:return count,False
    except ijson.JSONError:
        complete=False
    return count,complete

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--limit',type=int,default=20)
    ap.add_argument('--max-bytes',type=int,default=5_000_000)
    ap.add_argument('--min-bytes',type=int,default=0)
    ap.add_argument('--max-rows',type=int,default=50000)
    ap.add_argument('--source-timeout',type=int,default=120)
    a=ap.parse_args()
    codes=load_codes()
    adir=os.path.join(ROOT,'data','tic-attempts');os.makedirs(adir,exist_ok=True)
    done={os.path.basename(p)[:-5] for p in __import__('glob').glob(os.path.join(adir,'*.json'))}
    picked=[c for c in candidates(a.max_bytes) if key(c[1]) not in done and c[0]>=a.min_bytes][:a.limit]
    for size,url,name in picked:
        k=key(url);rec={'source_url':url,'locator_name':name,'locator_bytes':size,
                        'attempted_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
        out=os.path.join(ROOT,'data','tic',k+'.jsonl.gz')
        try:
            req=urllib.request.Request(url,headers=UA)
            with urllib.request.urlopen(req,timeout=a.source_timeout) as raw:
                stream,enc=stream_for(raw,None)
                if stream is None:
                    rec.update(status='skipped',reason='zip archive not handled by this extractor');raise StopIteration
                os.makedirs(os.path.dirname(out),exist_ok=True)
                with gzip.open(out+'.tmp','wt') as fh:n,complete=extract(stream,fh,codes,a.max_rows)
            os.replace(out+'.tmp',out)
            rec.update(status='ok' if n else 'empty',rows=n,complete_file_scan=complete,
                       code_filter=sorted(codes),container=enc,
                       output=os.path.relpath(out,ROOT),output_bytes=os.path.getsize(out))
            man={'source_url':url,'locator_name':name,'locator_bytes':size,'rows':n,
                 'complete_file_scan':complete,'code_filter':sorted(codes),
                 'extracted_at':rec['attempted_at'],'layer':'insurer-tic-in-network',
                 'patient_price_ready':False,
                 'caveats':['Provider references unresolved; no verified provider-directory join.',
                            'Plan identity from the locator file name only.',
                            'Capitation/bundle rows carry their negotiation_arrangement qualifier and are not per-service prices.',
                            'Truncated outputs are marked incomplete.']}
            man['provider_references'],man['provider_reference_read']=read_provider_refs(url,a.source_timeout)
            json.dump(man,open(out.replace('.jsonl.gz','.manifest.json'),'w'),indent=2)
        except StopIteration:
            pass
        except Exception as e:
            rec.update(status='failed',error=repr(e)[-500:])
        json.dump(rec,open(os.path.join(adir,k+'.json'),'w'),indent=2)
        print(rec['status'],size,name[:70],rec.get('rows',''))
    print('tranche done:',len(picked),'attempted')
if __name__=='__main__':main()
