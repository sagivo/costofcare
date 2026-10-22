"""Shared fail-closed validity checks for lossy search summaries, not source truth."""
import math
def issues(d):
 out=[]
 for code,r in d.get('codes',{}).items():
  for low,high in [('cash_min','cash_max'),('gross_min','gross_max'),('neg_min','neg_max')]:
   l,h=r.get(low),r.get(high)
   for field,value in [(low,l),(high,h)]:
    if value is not None and (isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0):out.append({'code':code,'flag':'invalid_numeric','field':field})
   if isinstance(l,(int,float)) and isinstance(h,(int,float)) and l>h:out.append({'code':code,'flag':'range_inverted','field':low})
  for payer,v in r.get('payers',{}).items():
   l,h=v.get('low'),v.get('high')
   if any(x is not None and (isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or x<0) for x in [l,h]):out.append({'code':code,'flag':'invalid_numeric','payer':payer})
   elif l is not None and h is not None and l>h:out.append({'code':code,'flag':'payer_range_inverted','payer':payer})
 return out
