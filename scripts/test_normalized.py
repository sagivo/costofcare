import unittest,tempfile,json,os,sys
import normalize_mrf as n
class NormalizedTests(unittest.TestCase):
 def test_qualifiers_survive(self):
  source={'standard_charge_information':[{'description':'Test','code_information':[{'code':'70551','type':'CPT'}],'modifiers':['26'],'standard_charges':[{'setting':'outpatient','billing_class':'professional','payers_information':[{'payer_name':'AETNA EXACT','plan_name':'EXACT PPO','standard_charge_dollar':125}]}]}]}
  with tempfile.NamedTemporaryFile(mode='w',delete=False) as f:json.dump(source,f);path=f.name
  try:
   rows=list(n.extract(path,{'70551':{}}));self.assertEqual(rows[0]['source_fields'],source['standard_charge_information'][0]);self.assertEqual(rows[0]['source_record_ordinal'],1)
  finally:os.unlink(path)
 def test_exact_csv_header_and_values_survive(self):
  content='description,code|1,code|1|type, median_amount \nMRI,70551,CPT,125\n'
  with tempfile.NamedTemporaryFile(mode='w',delete=False) as f:f.write(content);path=f.name
  try:
   rows=list(n.extract(path,{'70551':{}}))
   self.assertEqual(rows[0]['source_header'][-1],' median_amount ')
   self.assertEqual(rows[0]['source_values'],['MRI','70551','CPT','125'])
   self.assertEqual(rows[0]['source_record_ordinal'],1)
  finally:os.unlink(path)
 def test_no_non_cpt_false_match(self):
  source={'standard_charge_information':[{'code_information':[{'code':'70551','type':'CDM'}]}]}
  with tempfile.NamedTemporaryFile(mode='w',delete=False) as f:json.dump(source,f);path=f.name
  try:self.assertEqual(list(n.extract(path,{'70551':{}})),[])
  finally:os.unlink(path)
 def test_truncated_json_rejected(self):
  with tempfile.NamedTemporaryFile(mode='w',delete=False) as f:f.write('{"standard_charge_information":[{"code_information":[]}');path=f.name
  try:
   with self.assertRaises(Exception):list(n.extract(path,{'70551':{}}))
  finally:os.unlink(path)
if __name__=='__main__':unittest.main()
