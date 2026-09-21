import tempfile
import unittest
import io
import json
from pathlib import Path
from unittest.mock import patch
import benchmark as bm

class BenchmarkTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def batch(self):
        with patch.object(bm.POOL,'submit'):return bm.submit(self.root,dict(cases=bm.sample(),mode='demo'))
    def test_demo_explicit_no_tokens(self):
        b=self.batch();bm.work(self.root,b['id']);r=bm.get(self.root,b['id'])
        self.assertEqual(r['status'],'completed');self.assertEqual(len(r['results']),3)
        self.assertIsNone(r['results'][0]['usage']);self.assertIn('固定演示',r['results'][0]['answer'])
        self.assertIsNone(bm.summary(r)['pass_rate'])
    def test_rating_append_and_coverage(self):
        b=self.batch();bm.work(self.root,b['id']);d=dict(id=b['id'],case_id='T1',reviewer='测试评分人',reason='仅为评分接口验收',verdict='pass')
        bm.rate(self.root,d);r=bm.rate(self.root,dict(d,verdict='fail'))
        self.assertEqual(len(r['ratings']),2);self.assertEqual(bm.summary(r)['rated'],1);self.assertEqual(bm.summary(r)['pass_rate'],0)
        self.assertAlmostEqual(bm.summary(r)['coverage'],1/3)
    def test_active_batch_prevents_duplicate(self):
        self.batch()
        with self.assertRaises(ValueError):self.batch()
    def test_restart_preserves_pending(self):
        b=self.batch();bm.recover(self.root);r=bm.get(self.root,b['id']);self.assertEqual(r['status'],'interrupted');self.assertEqual(r['results'],[])
    def test_failed_call_no_rating(self):
        b=self.batch();b['mode']='live';bm.save(self.root,b)
        def fail(*args):raise ValueError('failure')
        bm.work(self.root,b['id'],fail)
        self.assertEqual(bm.summary(bm.get(self.root,b['id']))['successful'],0)
        with self.assertRaises(ValueError):bm.rate(self.root,dict(id=b['id'],case_id='T1',verdict='pass',reviewer='x',reason='x'))
    def test_invalid_cases(self):
        for cases in ([],bm.sample()*4,[dict(bm.sample()[0],origin='real')],[bm.sample()[0]]*2):
            with self.subTest(cases=cases),self.assertRaises(ValueError):bm.validate(cases)
    def test_blank_rating_rejected(self):
        b=self.batch();bm.work(self.root,b['id'])
        with self.assertRaises(ValueError):bm.rate(self.root,dict(id=b['id'],case_id='T1',verdict='pass',reviewer='',reason='x'))
    def test_truncated_empty_answer_retains_usage(self):
        data=dict(choices=[dict(message=dict(content=''),finish_reason='length')],usage=dict(total_tokens=1200),model='test')
        with patch.object(bm,'config',return_value=('test-key','test')),patch.object(bm,'urlopen',return_value=io.BytesIO(json.dumps(data).encode())):
            r=bm.call_model('test','test')
        self.assertEqual(r['status'],'incomplete');self.assertEqual(r['usage']['total_tokens'],1200)
