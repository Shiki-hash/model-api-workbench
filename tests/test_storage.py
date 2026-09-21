import copy
import json
import tempfile
import unittest
from pathlib import Path
from engine import generate
from server import sample
import storage

class Persistence(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.r=generate('数据库合成测试',sample());self.r.update(id='a'*32,task_id='a'*32,parent=None,round=0,created_at='2026-09-21T00:00:00Z')
    def tearDown(self):self.tmp.cleanup()
    def test_reopen_preserves_facts(self):
        storage.save(self.root,self.r)
        self.assertEqual(storage.get(self.root,self.r['id'])['facts'],self.r['facts'])
        db=storage.connect(self.root);self.assertEqual(db.execute('SELECT count(*) FROM facts').fetchone()[0],6);db.close()
    def test_legacy_import_once(self):
        (self.root/'old.json').write_text(json.dumps(self.r),encoding='utf-8')
        self.assertEqual(len(storage.history(self.root)),1);self.assertEqual(len(storage.history(self.root)),1)
        self.assertTrue((self.root/'old.json').exists())
    def test_version_is_immutable(self):
        storage.save(self.root,self.r);changed=copy.deepcopy(self.r);changed['topic']='changed'
        with self.assertRaises(ValueError):storage.save(self.root,changed)
        self.assertEqual(storage.get(self.root,self.r['id'])['topic'],self.r['topic'])
    def test_duplicate_approval_rejected(self):
        storage.save(self.root,self.r);self.r['status']='approved';self.r['reviewer']='test';storage.save(self.root,self.r)
        with self.assertRaises(ValueError):storage.save(self.root,self.r)
