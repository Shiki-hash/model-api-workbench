import unittest
from decimal import Decimal
from server import sample
from engine import generate
from costs import calculate

class CostsTests(unittest.TestCase):
    def setUp(self):self.a=dict(requests=10000,input_tokens=1000,output_tokens=500)
    def test_fees_and_threshold(self):
        r=calculate(sample(),self.a)
        self.assertEqual([Decimal(x['usd']) for x in r['rows']],[Decimal('30'),Decimal('29'),Decimal('29')])
        self.assertEqual(Decimal(r['thresholds'][1]['output_per_input']),Decimal('.375'))
        self.assertEqual(Decimal(r['thresholds'][2]['output_per_input']),Decimal('.5'))
    def test_missing_pair(self):self.assertEqual(calculate(sample()[:1],self.a)['rows'],[])
    def test_different_conditions(self):
        f=sample();f[0]['conditions']='缓存'
        r=calculate(f,self.a);self.assertEqual(len(r['rows']),2);self.assertEqual(len(r['gaps']),2)
    def test_invalid_assumptions(self):
        for bad in ('NaN','Infinity',-1,True,1.5,'',None):
            with self.subTest(bad=bad),self.assertRaises(ValueError):calculate(sample(),dict(self.a,requests=bad))
    def test_zero(self):self.assertEqual(Decimal(calculate(sample(),dict(self.a,requests=0))['rows'][0]['usd']),0)
    def test_report_persists_assumptions(self):
        r=generate('测试',sample(),assumptions=self.a)
        self.assertEqual(r['costs']['assumptions'],self.a);self.assertIn('30.0',r['report'])
    def test_bad_fact_no_calculation(self):
        f=sample();f[0]['value']=-1
        self.assertNotIn('costs',generate('测试',f,assumptions=self.a))
