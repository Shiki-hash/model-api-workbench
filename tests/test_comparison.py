import unittest
from copy import deepcopy
from comparison import compare
from benchmark import sample

class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.a=dict(id='a',cases=sample(),mode='live',status='completed',model='test',results=[],ratings=[],prompt_sha256='p')
        self.b=deepcopy(self.a);self.b['id']='b'
    def test_unrated_no_delta(self):self.assertIsNone(compare(self.a,self.b)['pass_delta_percentage_points'])
    def test_same_rejected(self):
        with self.assertRaises(ValueError):compare(self.a,self.a)
    def test_changed_rubric_rejected(self):
        self.b['cases'][0]['rubric']='different'
        with self.assertRaises(ValueError):compare(self.a,self.b)
    def test_mixed_mode_rejected(self):
        self.b['mode']='demo'
        with self.assertRaises(ValueError):compare(self.a,self.b)
    def test_paired_only(self):
        self.a['ratings']=[dict(case_id='T1',verdict='fail',reviewer='u'),dict(case_id='T2',verdict='pass',reviewer='u')]
        self.b['ratings']=[dict(case_id='T1',verdict='pass',reviewer='u')]
        r=compare(self.a,self.b);self.assertEqual(r['paired_count'],1);self.assertEqual(r['pass_delta_percentage_points'],100)
        self.assertAlmostEqual(r['paired_coverage'],1/3)
    def test_latest_rating(self):
        self.a['ratings']=[dict(case_id='T1',verdict='pass',reviewer='u'),dict(case_id='T1',verdict='fail',reviewer='u')]
        self.b['ratings']=[dict(case_id='T1',verdict='fail',reviewer='v')]
        r=compare(self.a,self.b);self.assertEqual(r['pass_delta_percentage_points'],0);self.assertTrue(any('评分人不同' in n for n in r['notes']))
