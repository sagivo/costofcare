"""Merge successful refresh output into a clean checkout of the latest branch."""
import os,json,glob,sys
root=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dest=sys.argv[1]
for src in glob.glob(root+'/data/hospitals/*.json'):
 d=json.load(open(src));target=dest+'/data/hospitals/'+os.path.basename(src)
 previous=json.load(open(target)) if os.path.exists(target) else {}
 if previous.get('status')=='ok' and d.get('status')!='ok': continue
 if d.get('extracted_at','')>=previous.get('extracted_at',''):
  os.makedirs(os.path.dirname(target),exist_ok=True);json.dump(d,open(target,'w'))
a=json.load(open(root+'/data/registry.json'));b=json.load(open(dest+'/data/registry.json'))
records={r['id']:r for r in b['records']}
for r in a['records']:records.setdefault(r['id'],r)
b['records']=list(records.values());b['directory_ids_checked']=sorted(set(a.get('directory_ids_checked',[])+b.get('directory_ids_checked',[])))
json.dump(b,open(dest+'/data/registry.json','w'))
