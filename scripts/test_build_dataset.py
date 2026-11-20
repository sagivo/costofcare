import json,os,tempfile,unittest
from build_dataset import build,TruncatedArtifactsError
OBS='2026-11-20T08:20:00Z'
NEW='2026-11-21T00:00:00Z'
VERIFIED={'method':'content-length','expected':100,'received':100}
def hospital(i,extracted_at,download_completeness=None):
 h={'id':i,'status':'ok','mrf_url':'https://example.test/%s.csv'%i,'display_name':i,'city':'C','state':'ST','extracted_at':extracted_at,'codes':{'99213':{'cash_min':10.0}}}
 if download_completeness is not None: h['download_completeness']=download_completeness
 return h
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
  r=self.make([hospital('redone','2026-11-21T00:00:00Z',VERIFIED)],listed=['redone'])
  out,summary=self.run_build(r)
  self.assertEqual([p['id'] for p in out['providers']],['redone'])
  self.assertEqual(out['excluded_incomplete'],[]); self.assertEqual(summary['excluded_incomplete'],0)
 def assert_stays_excluded(self,h):
  out,summary=self.run_build(self.make([h],listed=[h['id']]))
  self.assertEqual(out['providers'],[]); self.assertEqual(out['excluded_incomplete'],[h['id']]); self.assertEqual(summary['excluded_incomplete'],1)
 def test_d_newer_without_download_completeness_stays_excluded(self):
  self.assert_stays_excluded(hospital('nodc',NEW))
 def test_e_newer_close_delimited_unverified_stays_excluded(self):
  self.assert_stays_excluded(hospital('cd',NEW,{'method':'close-delimited-unverified','expected':None,'received':100}))
 def test_f_newer_verified_content_length_lifts(self):
  out,summary=self.run_build(self.make([hospital('cl',NEW,{'method':'content-length','expected':100,'received':100})],listed=['cl']))
  self.assertEqual([p['id'] for p in out['providers']],['cl']); self.assertEqual(out['excluded_incomplete'],[])
 def test_g_newer_content_length_mismatch_stays_excluded(self):
  self.assert_stays_excluded(hospital('mm',NEW,{'method':'content-length','expected':100,'received':99}))
 def test_chunked_framing_lifts_without_sizes(self):
  out,_=self.run_build(self.make([hospital('ch',NEW,{'method':'chunked-framing','expected':None,'received':100})],listed=['ch']))
  self.assertEqual([p['id'] for p in out['providers']],['ch'])
 def test_other_evidence_failures_stay_excluded(self):
  bad=[('str',{'method':'content-length','expected':'100','received':'100'}),('bool',{'method':'content-length','expected':True,'received':True}),
   ('none',{'method':'ranged-content-range-verified','expected':None,'received':None}),('unk',{'method':'bogus','expected':1,'received':1}),('notdict','content-length')]
  for i,c in bad: self.assert_stays_excluded(hospital(i,NEW,c))
 def test_verified_but_not_newer_or_unparseable_stays_excluded(self):
  self.assert_stays_excluded(hospital('eq',OBS,VERIFIED))
  self.assert_stays_excluded(hospital('old','2026-11-19T00:00:00Z',VERIFIED))
  self.assert_stays_excluded(hospital('junk','not-a-time',VERIFIED))
 def write_raw(self,r,text): open(r+'/data/truncated-artifacts.json','w').write(text)
 def assert_refuses(self,r):
  with self.assertRaises(TruncatedArtifactsError): self.run_build(r)
  self.assertFalse(os.path.exists(r+'/public/data/dataset.json')); self.assertFalse(os.path.exists(r+'/src/data/summary.json'))
 def test_missing_file_raises(self):
  self.assert_refuses(self.make([hospital('a','2026-11-19T20:00:00Z')]))
 def test_malformed_json_raises(self):
  r=self.make([hospital('a','2026-11-19T20:00:00Z')]); self.write_raw(r,'{"artifacts": ['); self.assert_refuses(r)
 def test_artifacts_not_a_list_raises(self):
  for v in ['{"artifacts": {}}','{"artifacts": null}','{"artifacts": "a"}','{}','[]']:
   r=self.make([hospital('a','2026-11-19T20:00:00Z')]); self.write_raw(r,v); self.assert_refuses(r)
 def test_entry_missing_or_invalid_fields_raises(self):
  for e in [{'observed_at':OBS},{'id':'','observed_at':OBS},{'id':5,'observed_at':OBS},{'id':'a'},{'id':'a','observed_at':''},{'id':'a','observed_at':None},'a']:
   r=self.make([hospital('a','2026-11-19T20:00:00Z')]); self.write_raw(r,json.dumps({'artifacts':[e]})); self.assert_refuses(r)
 def test_explicit_empty_list_builds_with_no_exclusions(self):
  r=self.make([hospital('a','2026-11-19T20:00:00Z'),hospital('b','2026-11-19T20:00:00Z')],listed=[])
  out,summary=self.run_build(r)
  self.assertEqual([p['id'] for p in out['providers']],['a','b'])
  self.assertEqual(out['excluded_incomplete'],[]); self.assertEqual(summary['excluded_incomplete'],0)
 def test_excluded_ids_sorted_and_shared_url(self):
  hs=[hospital('z','2026-11-19T20:00:00Z'),hospital('y','2026-11-19T20:00:00Z')]
  for h in hs: h['mrf_url']='https://example.test/shared.csv'
  out,_=self.run_build(self.make(hs,listed=['z','y']))
  self.assertEqual(out['excluded_incomplete'],['y','z']); self.assertEqual(out['providers'],[])
if __name__=='__main__':unittest.main()
