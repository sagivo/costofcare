#!/usr/bin/env python3
"""Non-destructive field-level QA of preserved original hospital records.
Flags source issues for review, never rewrites monetary values or invents joins.
"""
import collections,datetime,gzip,glob,json,os,re
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MONEY=re.compile(r'^standard_charge\|(?:gross|discounted_cash|min|max|.*\|negotiated_dollar|negotiated_dollar)$')
def main():
 counts=collections.Counter(); examples=[];records=0;coverage=collections.Counter()
 def flag(kind,r,field,value):
  counts[kind]+=1
  if sum(x['flag']==kind for x in examples)<20:examples.append({'flag':kind,'source_id':r['source_id'],'source_record_ordinal':r['source_record_ordinal'],'source_sha256':r['source_sha256'],'field':field,'raw_value':value})
 for p in glob.glob(ROOT+'/data/normalized/*.jsonl.gz'):
  with gzip.open(p,'rt') as f:
   for line in f:
    r=json.loads(line);records+=1
    if r['source_format']=='cms-csv':
     pairs=list(zip(r['source_header'],r['source_values']));values=dict(pairs)
     for key in ['setting','billing_class','modifiers','payer_name','plan_name']:
      if values.get(key,'').strip():coverage[key]+=1
     for key,v in pairs:
      if not MONEY.match(key) or not v.strip():continue
      try:
       n=float(v.strip().replace('$','').replace(',',''))
       if n<0:flag('negative_published_amount',r,key,v)
       elif n==0:flag('zero_published_amount_review',r,key,v)
       elif n>1_000_000:flag('large_published_amount_review',r,key,v)
      except ValueError:flag('nonnumeric_published_dollar_field',r,key,v)
    else:
     for sc in r['source_fields'].get('standard_charges',[]):
      for key in ['setting','billing_class']:
       if sc.get(key):coverage[key]+=1
      for key in ['gross_charge','discounted_cash','minimum','maximum']:
       v=sc.get(key)
       if isinstance(v,(float,int)) and v<0:flag('negative_published_amount',r,key,v)
      for pi in sc.get('payers_information',[]):
       for key in ['payer_name','plan_name','methodology']:
        if pi.get(key):coverage['json_'+key]+=1
       value=pi.get('standard_charge_dollar')
       if value is not None:
        if not isinstance(value,(int,float)):flag('nonnumeric_published_dollar_field',r,'standard_charge_dollar',value)
        elif value<0:flag('negative_published_amount',r,'standard_charge_dollar',value)
        elif value==0:flag('zero_published_amount_review',r,'standard_charge_dollar',value)
        elif value>1_000_000:flag('large_published_amount_review',r,'standard_charge_dollar',value)
     coverage['json_source_records']+=1
 report={'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'records_scanned':records,'flag_counts':dict(counts),'review_examples':examples,'populated_qualifier_counts':dict(coverage),'interpretation':'Counts are field occurrences, not independent errors or comparable rates. Thresholds are review rules, not grounds to overwrite source facts. Original data is unchanged.'}
 json.dump(report,open(ROOT+'/data/quality/semantic-review.json','w'),indent=2);print(records,'records scanned',dict(counts))
if __name__=='__main__':main()
