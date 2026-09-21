import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from uuid import uuid4
import storage
import sources
from engine import generate
from model_client import analyze

POOL=ThreadPoolExecutor(max_workers=1)
GUARD=threading.Lock()

def now():return datetime.now(timezone.utc).isoformat()

def db(root):
    c=storage.connect(root)
    c.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,payload TEXT NOT NULL)');c.commit();return c

def persist(root,j):
    c=db(root)
    try:
        with c:c.execute('INSERT OR REPLACE INTO jobs VALUES(?,?)',(j['id'],json.dumps(j,ensure_ascii=False)))
    finally:c.close()

def get(root,id):
    c=db(root)
    try:r=c.execute('SELECT payload FROM jobs WHERE id=?',(id,)).fetchone()
    finally:c.close()
    if not r:raise ValueError('后台任务不存在。')
    return json.loads(r[0])

def recent(root):
    c=db(root)
    try:return sorted([json.loads(r[0]) for r in c.execute('SELECT payload FROM jobs')],key=lambda j:j['created_at'],reverse=True)
    finally:c.close()

def recover(root):
    for j in recent(root):
        if j['status'] in ['queued','running']:
            j.update(status='failed',error='服务重启中断；结果与费用需核对，可手动重试。');persist(root,j)

def submit(root,data,retry_of=None):
    with GUARD:
        attempt=0
        if retry_of:
            old=get(root,retry_of)
            if old['status']!='failed' or old['attempt']>=2:raise ValueError('仅失败任务可重试，最多两次。')
            if any(j.get('retry_of')==retry_of for j in recent(root)):raise ValueError('该失败任务已重试，请查看后续任务。')
            data=old['input'];attempt=old['attempt']+1
        if sum(j['status'] in ['queued','running'] for j in recent(root))>=3:raise ValueError('已有3个后台任务，请稍后提交。')
        sources.verify(root,data.get('facts'))
        preflight=generate(data.get('topic'),data.get('facts'),assumptions=data.get('assumptions'),brief=data.get('brief'))
        if preflight['issues']:raise ValueError('资料检查未通过，请先使用离线检查修复事实卡。')
        parent=storage.get(root,data['parent']) if data.get('parent') else None
        if parent and parent['round']>=2:raise ValueError('报告已达两次修订上限。')
        j=dict(id=uuid4().hex,status='queued',created_at=now(),input=data,attempt=attempt,retry_of=retry_of,events=[],result_id=None,error=None)
        persist(root,j);POOL.submit(work,root,j);return j

def work(root,j,client=analyze):
    start=time.monotonic()
    def log(stage,**meta):
        j['events'].append(dict(time=now(),stage=stage,**meta));persist(root,j)
    try:
        j['status']='running';log('检查输入与证据')
        data=j['input'];r=generate(data['topic'],data['facts'],assumptions=data.get('assumptions'),brief=data.get('brief'))
        if r['issues']:raise ValueError('等待期间资料已过期或不合格。')
        output=client(data['topic'],data['facts'],log)
        log('引用检查通过，组装报告')
        r['report']=r['report'].replace('运行方式：离线规则与模板；未调用大模型，未访问来源网站。','运行方式：DeepSeek分析＋确定性引用检查；未访问来源网站。')
        r['report']+='\n\n## 模型辅助分析（待人工核查）\n'
        for item in output['insights']:
            r['report']+='\n'+item['text']+'\n'+ '\n'.join(f"- {e['fact_id']}：{e['quote']}" for e in item['evidence'])+'\n'
        r['report']+='\n## 模型提示的缺口\n'+'\n'.join('- '+x for x in output['caveats'])
        parent=storage.get(root,data['parent']) if data.get('parent') else None
        id=uuid4().hex;r.update(id=id,task_id=parent['task_id'] if parent else id,parent=data.get('parent'),round=parent['round']+1 if parent else 0,created_at=now(),mode='live_model',analysis=output,job_id=j['id'])
        storage.save(root,r);j.update(status='succeeded',result_id=id);log('报告已保存，等待人工确认')
    except Exception as e:
        j.update(status='failed',error=str(e) if isinstance(e,ValueError) else '后台处理失败，原有版本保留。')
        log('任务失败，禁止自动确认')
    finally:j['elapsed_seconds']=round(time.monotonic()-start,2);persist(root,j)
