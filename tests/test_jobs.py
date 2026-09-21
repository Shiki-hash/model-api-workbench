import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import jobs,storage
from server import sample
from model_client import validate_output

class Background(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def create(self):
        with patch.object(jobs.POOL,'submit'):return jobs.submit(self.root,{'topic':'合成后台测试','facts':sample()})
    def test_timeout_never_creates_approved_report(self):
        j=self.create()
        def fail(*args):raise ValueError('超时')
        jobs.work(self.root,j,fail)
        self.assertEqual(jobs.get(self.root,j['id'])['status'],'failed');self.assertEqual(storage.history(self.root),[])
    def test_success_requires_human(self):
        j=self.create()
        def ok(topic,facts,log):return {'insights':[{'text':'合成演示','evidence':[{'fact_id':'S1','quote':facts[0]['source_excerpt']}]}],'caveats':['待核查']}
        jobs.work(self.root,j,ok);done=jobs.get(self.root,j['id'])
        self.assertEqual(storage.get(self.root,done['result_id'])['status'],'awaiting_human')
    def test_restart_interruption(self):
        j=self.create();jobs.recover(self.root);self.assertEqual(jobs.get(self.root,j['id'])['status'],'failed')
    def test_duplicate_retry(self):
        j=self.create();jobs.recover(self.root)
        with patch.object(jobs.POOL,'submit'):
            jobs.submit(self.root,{},j['id'])
            with self.assertRaises(ValueError):jobs.submit(self.root,{},j['id'])
    def test_unbacked_citation(self):
        with self.assertRaises(ValueError):validate_output({'insights':[{'text':'最低价','evidence':[{'fact_id':'S1','quote':'编造原文'}]}],'caveats':[]},sample())
    def test_input_failure_before_enqueue(self):
        f=sample();f[0]['value']=None
        with self.assertRaises(ValueError):jobs.submit(self.root,{'topic':'任务','facts':f})
