#!/usr/bin/env python3
"""Stream an explicitly selected TiC file into auditable JSONL, without invented joins.
Requires ijson. Keeps provider reference IDs and inline provider groups; a separate
verified provider directory join is required before exposing local provider prices.
Only dollar negotiated prices are extracted. Allowed-amount files have a different
schema and are intentionally not silently interpreted as in-network prices.
"""
import argparse,gzip,io,json,os,urllib.request,time
import ijson

def extract(stream,output,codes=None,max_rows=100000):
 count=0
 for item in ijson.items(stream,'in_network.item',use_float=True):
  code=str(item.get('billing_code',''))
  if codes and code not in codes:continue
  for rate in item.get('negotiated_rates',[]):
   for p in rate.get('negotiated_prices',[]):
    amount=p.get('negotiated_rate')
    if amount is None or p.get('negotiated_type') not in ['negotiated','fee schedule','derived']:continue
    # Explicitly retain type and all qualifiers, never mix into a generic price.
    row={'billing_code':code,'billing_code_type':item.get('billing_code_type'),'description':item.get('description'),'negotiation_arrangement':item.get('negotiation_arrangement'),'provider_references':rate.get('provider_references'),'provider_groups':rate.get('provider_groups'),'price':p}
    output.write(json.dumps(row,separators=(',',':'))+'\n');count+=1
    if max_rows and count>=max_rows:return count,False
 return count,True

def main():
 p=argparse.ArgumentParser();p.add_argument('--url',required=True);p.add_argument('--out',required=True);p.add_argument('--codes');p.add_argument('--max-rows',type=int,default=100000);a=p.parse_args()
 os.makedirs(os.path.dirname(os.path.abspath(a.out)),exist_ok=True)
 with urllib.request.urlopen(urllib.request.Request(a.url,headers={'User-Agent':'CostOfCare TiC research/1.0'}),timeout=90) as raw:
  buffered=io.BufferedReader(raw);stream=gzip.GzipFile(fileobj=buffered) if buffered.peek(2)[:2]==b'\x1f\x8b' else buffered
  with gzip.open(a.out+'.tmp','wt') as output:n,complete=extract(stream,output,set(a.codes.split(',')) if a.codes else None,a.max_rows)
 os.replace(a.out+'.tmp',a.out)
 json.dump({'source_url':a.url,'extracted_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'rows':n,'complete_file_scan':complete,'patient_price_ready':False,'caveat':'Provider references, plan identity and rate qualifiers require verified joins. Truncated outputs are marked incomplete.'},open(a.out+'.manifest.json','w'),indent=2)
 print(n,'rows; complete scan:',complete)
if __name__=='__main__':main()
