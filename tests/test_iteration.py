import tempfile
import unittest
import json
import io
from pathlib import Path
from unittest.mock import patch
import benchmark as bm

class IterationTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def submit(self,**kw):
        with patch.object(bm.POOL,'submit'):return bm.submit(self.root,dict(cases=bm.sample(),mode='demo',**kw))
    def test_snapshot_and_parent(self):
        a=self.submit();bm.work(self.root,a['id'])
        b=self.submit(parent_id=a['id'],change_reason='减少承诺',prompt='仅核查，不承诺功能',max_tokens=3000)
        self.assertEqual(b['parent_id'],a['id']);self.assertEqual(b['request_settings']['max_tokens'],3000)
        self.assertNotEqual(a['prompt_sha256'],b['prompt_sha256']);self.assertEqual(a['dataset_sha256'],b['dataset_sha256'])
        self.assertEqual(bm.get(self.root,a['id'])['prompt'],a['prompt'])
    def test_empty_change_reason_rejected(self):
        a=self.submit();bm.work(self.root,a['id'])
        with self.assertRaises(ValueError):self.submit(parent_id=a['id'])
    def test_invalid_settings(self):
        for kw in ({'prompt':''},{'max_tokens':True},{'max_tokens':5000},{'max_tokens':1.5}):
            with self.subTest(kw=kw),self.assertRaises(ValueError):self.submit(**kw)
    def test_worker_uses_snapshot(self):
        a=self.submit(prompt='保存的提示词',max_tokens=3000);a['mode']='live';bm.save(self.root,a)
        calls=[]
        def client(*args):calls.append(args);return dict(status='succeeded',answer='测试回答',usage=None)
        with patch.object(bm,'PROMPT','后来修改的默认值'):bm.work(self.root,a['id'],client)
        self.assertEqual(calls[0][2:4],('保存的提示词',3000))
    def test_request_contains_saved_parameters(self):
        response=dict(choices=[dict(message=dict(content='answer'),finish_reason='stop')])
        with patch.object(bm,'config',return_value=('test','model')),patch.object(bm,'urlopen',return_value=io.BytesIO(json.dumps(response).encode())) as opener:
            bm.call_model('input','model','my prompt',3000)
        body=json.loads(opener.call_args.args[0].data)
        self.assertEqual(body['messages'][0]['content'],'my prompt');self.assertEqual(body['max_tokens'],3000)
