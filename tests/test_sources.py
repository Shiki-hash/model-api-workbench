import json
import tempfile
import unittest
from pathlib import Path
import sources
import storage

class SourceTests(unittest.TestCase):
    def test_unknown_source(self):
        with self.assertRaises(ValueError):sources.fetch(Path('.'),'http://127.0.0.1')
    def test_html_script_excluded_table_preserved(self):
        p=sources.Text();p.feed('<script>ignore()</script><tr><td>Input</td><td>$1</td></tr>')
        self.assertEqual(''.join(p.parts),'\n | Input | $1')
    def test_snapshot_reference(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);c=storage.connect(root)
            s=dict(url='https://example.com',retrieved_at='2026-09-21T00:00:00Z',text='Input price $1')
            c.execute('CREATE TABLE sources(id TEXT PRIMARY KEY,payload TEXT)')
            c.execute('INSERT INTO sources VALUES(?,?)',('abc',json.dumps(s)));c.commit();c.close()
            f=dict(source_snapshot_id='abc',source_url=s['url'],retrieved_at='2026-09-21',source_excerpt='price $1')
            sources.verify(root,[f])
            with self.assertRaises(ValueError):sources.verify(root,[dict(f,source_excerpt='price $2')])
    def test_redirect_rejected(self):
        with self.assertRaises(ValueError):sources.NoRedirect().redirect_request(None)
