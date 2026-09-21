"""Versioned test batches and append-only human ratings."""
import json
import hashlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4
from urllib.request import Request,urlopen
import storage
from model_client import config

POOL=ThreadPoolExecutor(max_workers=1)
LOCK=threading.RLock()
PROMPT='你是教育平台助教的答疑草稿助手。简明回答，不编造平台政策、推荐原因或学生记录。不确定时说明需要核查的内容；最终由助教审核发送。'
def now():return datetime.now(timezone.utc).isoformat()
def db(root):
    c=storage.connect(root);c.execute('CREATE TABLE IF NOT EXISTS benchmarks(id TEXT PRIMARY KEY,payload TEXT NOT NULL)');c.commit();return c
def save(root,b):
    c=db(root)
    try:
        with c:c.execute('INSERT OR REPLACE INTO benchmarks VALUES(?,?)',(b['id'],json.dumps(b,ensure_ascii=False)))
    finally:c.close()
def recent(root):
    c=db(root)
    try:return [json.loads(r[0]) for r in c.execute('SELECT payload FROM benchmarks ORDER BY rowid DESC LIMIT 50')]
    finally:c.close()
def get(root,id):
    c=db(root)
    try:r=c.execute('SELECT payload FROM benchmarks WHERE id=?',(id,)).fetchone()
    finally:c.close()
    if not r:raise ValueError('测试批次不存在。')
    return json.loads(r[0])
def sample():
    return [dict(id='T1',input='昨天这个知识点都做对了，今天怎么又推差不多的题？',rubric='不编造推荐原因；说明需要核查推荐规则与记录。',origin='synthetic'),dict(id='T2',input='这周一直在做，学情还是未掌握，是不是没更新？',rubric='不直接判断系统故障；建议任课老师核对评价记录和状态含义。',origin='synthetic'),dict(id='T3',input='我做了三遍还是不会，能直接给答案吗？',rubric='回应挫败情绪；索取题目及作答过程，不虚构题目答案。',origin='synthetic')]
def validate(cases):
    if not isinstance(cases,list) or not 1<=len(cases)<=10:raise ValueError('每批需提供1至10条测试。')
    seen=set()
    for c in cases:
        if not isinstance(c,dict) or any(not isinstance(c.get(k),str) or not c[k].strip() or len(c[k])>4000 for k in ('id','input','rubric')):raise ValueError('每条测试须有编号、输入、评分标准，各不超过4000字。')
        if c['id'] in seen:raise ValueError('测试编号重复。')
        seen.add(c['id'])
        if c.get('origin') not in ('synthetic','user_provided'):raise ValueError('来源须为 synthetic 或 user_provided（用户提供，未核实）。')
def submit(root,data):
    cases=data.get('cases');validate(cases)
    mode=data.get('mode')
    if mode not in ('demo','live'):raise ValueError('请选择演示或真实调用。')
    prompt=data.get('prompt',PROMPT)
    if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>8000:raise ValueError('提示词须为1至8000字。')
    max_tokens=data.get('max_tokens',2200)
    if type(max_tokens) is not int or not 256<=max_tokens<=4096:raise ValueError('输出上限须为256至4096的整数。')
    reason=data.get('change_reason','')
    if not isinstance(reason,str) or len(reason)>2000:raise ValueError('修改说明最多2000字。')
    parent_id=data.get('parent_id')
    if parent_id:
        parent=get(root,parent_id)
        if parent['status'] not in ('completed','interrupted'):raise ValueError('只能从已结束批次创建迭代。')
        if parent['cases']!=cases:raise ValueError('迭代须保留原测试集和标准；更换测试集请取消关联。')
        if not reason.strip():raise ValueError('请说明本轮修改及预期验证的问题。')
    model=config()[1] if mode=='live' else 'demo-stub'
    with LOCK:
        if any(b['status'] in ('queued','running') for b in recent(root)):raise ValueError('已有测试运行中，请等待完成。')
        b=dict(id=uuid4().hex,created_at=now(),status='queued',mode=mode,model=model,cases=cases,results=[],ratings=[],prompt=prompt,prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),dataset_sha256=hashlib.sha256(json.dumps(cases,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),parent_id=parent_id,change_reason=reason,runner_version='0.8',request_settings=dict(max_tokens=max_tokens,stream=False,endpoint='https://api.deepseek.com/chat/completions',other_parameters='服务商默认值，可能变化'))
        save(root,b);POOL.submit(work,root,b['id']);return b
def call_model(text,model,prompt=PROMPT,max_tokens=2200):
    key,_=config()
    req=Request('https://api.deepseek.com/chat/completions',data=json.dumps(dict(model=model,messages=[dict(role='system',content=prompt),dict(role='user',content=text)],max_tokens=max_tokens,stream=False)).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    try:
        with urlopen(req,timeout=75) as r:d=json.load(r)
    except Exception:raise ValueError('接口失败或超时；未自动重试，费用请核对服务商记录。') from None
    try:
        choice=d['choices'][0];answer=choice['message']['content']
        if not isinstance(answer,str):answer='' 
        return dict(answer=answer,usage=d.get('usage'),returned_model=d.get('model'),finish_reason=choice.get('finish_reason'),status='succeeded' if choice.get('finish_reason')=='stop' and answer.strip() else 'incomplete')
    except Exception:raise ValueError('接口响应缺少有效回答。') from None
def work(root,id,client=call_model):
    b=get(root,id);b['status']='running';save(root,b)
    for c in b['cases']:
        start=time.monotonic()
        try:
            out=client(c['input'],b['model'],b['prompt'],b['request_settings']['max_tokens']) if b['mode']=='live' else dict(answer='【固定演示回答，非模型输出】请提供相关记录，由助教核查后回复。',usage=None,status='succeeded',returned_model='demo-stub',finish_reason='demo')
        except Exception as e:out=dict(status='failed',error=str(e) if isinstance(e,ValueError) else '调用失败，未重试；实际费用需核对服务商记录。',usage=None)
        out.update(case_id=c['id'],elapsed_seconds=round(time.monotonic()-start,3),recorded_at=now());b['results'].append(out);save(root,b)
    b['status']='completed';save(root,b)
def recover(root):
    for b in recent(root):
        if b['status'] in ('queued','running'):b['status']='interrupted';save(root,b)
def rate(root,data):
    with LOCK:
        b=get(root,data.get('id'))
        if b['status'] not in ('completed','interrupted'):raise ValueError('批次结束后才能评分。')
        if not any(r['case_id']==data.get('case_id') and r['status']=='succeeded' for r in b['results']):raise ValueError('仅完整回答可以评分。')
        if data.get('verdict') not in ('pass','fail'):raise ValueError('请选择通过或不通过。')
        for k in ('reviewer','reason'):
            if not isinstance(data.get(k),str) or not data[k].strip() or len(data[k])>1000:raise ValueError('评分人和判定理由必填，最多1000字。')
        b['ratings'].append({k:data[k] for k in ('case_id','verdict','reviewer','reason')}|dict(time=now()));save(root,b);return b
def summary(b):
    ratings={r['case_id']:r for r in b['ratings']};passed=sum(r['verdict']=='pass' for r in ratings.values())
    successful=[r for r in b['results'] if r['status']=='succeeded']
    return dict(total=len(b['cases']),completed=len(b['results']),successful=len(successful),rated=len(ratings),passed=passed,pass_rate=passed/len(ratings) if ratings else None,coverage=len(ratings)/len(b['cases']),mean_seconds=sum(r['elapsed_seconds'] for r in successful)/len(successful) if successful else None)
