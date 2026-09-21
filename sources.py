"""Fetch a fixed catalog of public official pages, preserving an immutable snapshot."""
import hashlib
import json
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.request import Request, build_opener, HTTPRedirectHandler
from uuid import uuid4
import storage

CATALOG={'deepseek':'https://api-docs.deepseek.com/quick_start/pricing/', 'anthropic':'https://platform.claude.com/docs/en/about-claude/pricing'}

def get(root, id):
    c=storage.connect(root)
    try:
        c.execute('CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY,payload TEXT NOT NULL)')
        row=c.execute('SELECT payload FROM sources WHERE id=?',(id,)).fetchone()
    finally:c.close()
    if not row:raise ValueError('来源快照不存在。')
    return json.loads(row[0])

def verify(root, facts):
    if not isinstance(facts,list):return
    for f in facts:
        if not isinstance(f,dict) or not f.get('source_snapshot_id'):continue
        s=get(root,f['source_snapshot_id'])
        if f.get('source_url')!=s['url'] or f.get('retrieved_at')!=s['retrieved_at'][:10] or not f.get('source_excerpt') or f['source_excerpt'] not in s['text']:
            raise ValueError('事实卡的链接、日期或原文与采集快照不一致，请核对。')

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError('官方页面发生跳转，请更新固定来源目录后重试。')

class Text(HTMLParser):
    def __init__(self):super().__init__();self.parts=[];self.hidden=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.hidden+=1
        if tag in ('p','tr','div','h1','h2','h3','li','br'):self.parts.append('\n')
        if tag in ('td','th'):self.parts.append(' | ')
    def handle_endtag(self,tag):
        if tag in ('script','style'):self.hidden=max(0,self.hidden-1)
    def handle_data(self,data):
        if not self.hidden:self.parts.append(data)

def fetch(root, provider):
    if provider not in CATALOG:raise ValueError('请选择目录内的官方来源。')
    url=CATALOG[provider]
    try:
        with build_opener(NoRedirect()).open(Request(url,headers={'User-Agent':'APIResearchWorkbench/0.4'}),timeout=20) as r:
            if 'text/html' not in r.headers.get('Content-Type',''):raise ValueError('来源未返回 HTML。')
            raw=r.read(2_000_001)
        if len(raw)>2_000_000:raise ValueError('来源页面超过 2MB，未保存。')
        parser=Text();parser.feed(raw.decode('utf-8'))
        content='\n'.join(line.strip() for line in ''.join(parser.parts).splitlines() if line.strip())
        if len(content)<100:raise ValueError('来源正文不足，请人工打开官方页面核查。')
    except ValueError:raise
    except Exception:raise ValueError('官方资料采集失败，请稍后重试或手动核查链接。')
    snapshot=dict(id=uuid4().hex,provider=provider,url=url,retrieved_at=datetime.now(timezone.utc).isoformat(),sha256=hashlib.sha256(raw).hexdigest(),text=content)
    c=storage.connect(root)
    try:
        with c:
            c.execute('CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY,payload TEXT NOT NULL)')
            c.execute('INSERT INTO sources VALUES(?,?)',(snapshot['id'],json.dumps(snapshot,ensure_ascii=False)))
    finally:c.close()
    return snapshot
