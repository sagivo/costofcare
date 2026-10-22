import unittest
from summary_validation import issues
class ValidationTests(unittest.TestCase):
 def test_valid(self):self.assertEqual(issues({'codes':{'1':{'cash_min':1,'cash_max':2}}}),[])
 def test_inverted(self):self.assertTrue(issues({'codes':{'1':{'cash_min':2,'cash_max':1}}}))
 def test_invalid_high(self):self.assertTrue(issues({'codes':{'1':{'gross_max':float('nan')}}}))
 def test_invalid_payer(self):self.assertTrue(issues({'codes':{'1':{'payers':{'x':{'low':-1,'high':2}}}}}))
if __name__=='__main__':unittest.main()
