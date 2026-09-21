import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import server

class HttpFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.old=server.STORE;server.STORE=Path(cls.tmp.name)
        cls.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        cls.base=f'http://127.0.0.1:{cls.http.server_port}'
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();cls.thread.join();server.STORE=cls.old;cls.tmp.cleanup()
    def req(self,path,data=None):
        request=Request(self.base+path,data=json.dumps(data).encode() if data else None,headers={'Content-Type':'application/json'})
        try:
            with urlopen(request) as r:return r.status,r.read().decode()
        except HTTPError as e:return e.code,e.read().decode()
    def new(self,f=None,parent=None):
        status,body=self.req('/api/run',{'topic':'HTTP合成验收','facts':f if f is not None else server.sample(),'parent':parent})
        self.assertEqual(status,200);return json.loads(body)
    def test_export_gate_and_confirmation(self):
        r=self.new();self.assertEqual(self.req('/api/export/'+r['id'])[0],409)
        self.assertEqual(self.req('/api/approve',{'id':r['id'],'reviewer':'HTTP合成验收','confirmed':True})[0],200)
        status,body=self.req('/api/export/'+r['id']);self.assertEqual(status,200);self.assertIn('synthetic',body)
    def test_blocked_approval_rejected(self):
        f=server.sample();f[0]['source_url']='';r=self.new(f)
        self.assertEqual(self.req('/api/approve',{'id':r['id'],'reviewer':'test','confirmed':True})[0],400)
    def test_revision_cap_and_original(self):
        a=self.new();b=self.new(parent=a['id']);c=self.new(parent=b['id'])
        self.assertEqual(self.req('/api/run',{'topic':'test','facts':server.sample(),'parent':c['id']})[0],400)
        self.assertEqual(server.load(a['id'])['round'],0)
    def test_path_traversal_rejected(self):self.assertEqual(self.req('/api/export/..')[0],404)
