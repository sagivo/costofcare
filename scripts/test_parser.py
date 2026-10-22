import unittest,io,sys
import mrf_extract as m
class ParserTests(unittest.TestCase):
 def test_json(self):
  s='{"hospital_name":"Test","standard_charge_information":[{"description":"MRI","code_information":[{"code":"70551","type":"CPT"}],"standard_charges":[{"discounted_cash":250,"payers_information":[{"payer_name":"Aetna","plan_name":"PPO","standard_charge_dollar":180}]}]}]}'
  a,_=m.extract_json(io.StringIO(s),{'70551':{}})
  self.assertEqual(a['70551'].out()['cash_min'],250)
  self.assertEqual(a['70551'].out()['payers']['Aetna']['low'],180)
 def test_truncated(self):
  with self.assertRaises(ValueError):list(m.iter_array_items(io.StringIO('{"standard_charge_information":[{"x":1'), 'standard_charge_information'))
 def test_csv(self):
  s='hospital_name,last_updated_on\nTest,2026-10-20\ndescription,code|1,code|1|type,standard_charge|discounted_cash,payer_name,plan_name,standard_charge|negotiated_dollar\nMRI,70551,CPT,250,Aetna,PPO,180\n'
  a,meta=m.extract_csv(io.StringIO(s),{'70551':{}})
  self.assertEqual(meta['hospital_name'],'Test');self.assertEqual(a['70551'].out()['payers']['Aetna']['low'],180)
 def test_no_algorithm_conversion(self):
  a=m.Acc();a.add_payer('Aetna','PPO',pct=80,algo='80% billed');self.assertFalse(a.payers)
if __name__=='__main__':unittest.main()
