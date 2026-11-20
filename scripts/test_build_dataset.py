import json,os,tempfile,unittest
from build_dataset import build
OBS='2026-11-20T08:20:00Z'
def hospital(i,extracted_at):
 return {'id':i,'status':'ok','mrf_url':'https://example.test/%s.csv'%i,'display_name':i,'city':'C','state':'ST','extracted_at':extracted_at,'codes':{'99213':{'cash_min':10.0}}}
class BuildDatasetTests(unittest.TestCase):
 def make(self,hospitals,listed=None):
  self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); r=self.tmp.name
  for sub in ['scripts','data/hospitals']: os.makedirs(r+'/'+sub)
  json.dump({'codes':['99213']},open(r+'/scripts/target_codes.json','w'))
  json.dump({'records':[]},open(r+'/data/registry.json','w'))
  for h in hospitals: json.dump(h,open(r+'/data/hospitals/%s.json'%h['id'],'w'))
  if listed is not None: json.dump({'artifacts':[{'id':i,'observed_at':OBS} for i in listed]},open(r+'/data/truncated-artifacts.json','w'))
  return r
 def run_build(self,r):
  import contextlib,io
  with contextlib.redirect_stdout(io.StringIO()): out,summary=build(r)
  self.assertEqual(json.load(open(r+'/public/data/dataset.json'))['excluded_incomplete'],out['excluded_incomplete'])
  self.assertEqual(json.load(open(r+'/src/data/summary.json')),summary)
  return out,summary
 def test_old_listed_artifact_excluded(self):
  r=self.make([hospital('bad','2026-11-19T20:00:00Z'),hospital('good','2026-11-19T20:00:00Z')],listed=['bad'])
  out,summary=self.run_build(r)
  self.assertEqual([p['id'] for p in out['providers']],['good'])
  self.assertEqual(out['excluded_incomplete'],['bad'])
  self.assertEqual(summary['excluded_incomplete'],1)
  self.assertEqual(summary['providers'],1); self.assertEqual(summary['rows'],1)
  self.assertEqual([a['id'] for a in out['attempts']],['bad','good'])
 def test_newer_artifact_lifts_exclusion(self):
  r=self.make([hospital('redone','2026-11-21T00:00:00Z')],listed=['redone'])
  out,summary=self.run_build(r)
  self.assertEqual([p['id'] for p in out['providers']],['redone'])
  self.assertEqual(out['excluded_incomplete'],[]); self.assertEqual(summary['excluded_incomplete'],0)
 def test_missing_file_changes_nothing(self):
  r=self.make([hospital('a','2026-11-19T20:00:00Z'),hospital('b','2026-11-19T20:00:00Z')])
  out,summary=self.run_build(r)
  self.assertEqual([p['id'] for p in out['providers']],['a','b'])
  self.assertEqual(out['excluded_incomplete'],[]); self.assertEqual(summary['excluded_incomplete'],0)
 def test_excluded_ids_sorted_and_shared_url(self):
  hs=[hospital('z','2026-11-19T20:00:00Z'),hospital('y','2026-11-19T20:00:00Z')]
  for h in hs: h['mrf_url']='https://example.test/shared.csv'
  out,_=self.run_build(self.make(hs,listed=['z','y']))
  self.assertEqual(out['excluded_incomplete'],['y','z']); self.assertEqual(out['providers'],[])
if __name__=='__main__':unittest.main()
