import json
import threading
from uuid import uuid4
from pathlib import Path
from datetime import datetime, timezone, date
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from engine import generate, approve
import storage
import jobs
import sources
import benchmark
import comparison

ROOT=Path(__file__).resolve().parent
STORE=ROOT/'runs'
STORE.mkdir(exist_ok=True)
LOCK=threading.Lock()


def sample():
    return [dict(fact_id=f'S{i}',provider=f'示例服务商{label}',model_id=f'demo-{label}-v1',
                 dimension=dim,value=value,unit='USD/1M tokens',conditions='合成示例：标准在线调用，不含缓存与批处理',
                 source_url=f'https://example.com/demo-{label}',source_excerpt=f'合成资料，{dim}={value} USD/1M tokens；不代表实际报价。',
                 retrieved_at=date.today().isoformat(),evidence_type='synthetic')
            for i,(label,dim,value) in enumerate([('A','input_price',1.2),('A','output_price',3.6),('B','input_price',0.8),('B','output_price',4.2),('C','input_price',1.5),('C','output_price',2.8)],1)]


def path_for(run_id):
    if not isinstance(run_id,str) or len(run_id)!=32 or any(c not in '0123456789abcdef' for c in run_id):
        raise ValueError('无效记录编号。')
    return STORE/(run_id+'.json')


def save(run):
    storage.save(STORE,run)


def load(run_id):
    path_for(run_id)
    return storage.get(STORE,run_id)


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def reply(self,status,body,kind='application/json; charset=utf-8'):
        raw=(json.dumps(body,ensure_ascii=False) if kind.startswith('application/json') else body).encode('utf-8')
        self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        try:
            if self.path=='/benchmark': return self.reply(200,(ROOT/'web/benchmark.html').read_text(encoding='utf-8'),'text/html; charset=utf-8')
            if self.path=='/api/benchmarks/defaults': return self.reply(200,dict(prompt=benchmark.PROMPT,max_tokens=2200))
            if self.path=='/api/benchmarks/information': return self.reply(200,json.loads((ROOT/'datasets/information-v1.json').read_text(encoding='utf-8')))
            if self.path=='/api/benchmarks/boundary': return self.reply(200,json.loads((ROOT/'datasets/boundary-v1.json').read_text(encoding='utf-8')))
            if self.path=='/api/benchmarks/sample': return self.reply(200,benchmark.sample())
            if self.path=='/api/benchmarks': return self.reply(200,[dict(b,summary=benchmark.summary(b)) for b in benchmark.recent(STORE)])
            if self.path=='/': return self.reply(200,(ROOT/'web/index.html').read_text(encoding='utf-8'),'text/html; charset=utf-8')
            if self.path.startswith('/api/sources/'):
                return self.reply(200,sources.get(STORE,self.path.rsplit('/',1)[-1]))
            if self.path=='/api/jobs': return self.reply(200,jobs.recent(STORE)[:30])
            if self.path.startswith('/api/jobs/'):
                job=jobs.get(STORE,self.path.rsplit('/',1)[-1]);return self.reply(200,dict(job,result=load(job['result_id']) if job.get('result_id') else None))
            if self.path=='/api/sample': return self.reply(200,sample())
            if self.path=='/api/history':
                records=storage.history(STORE)
                return self.reply(200,sorted(records,key=lambda x:x['created_at'],reverse=True)[:30])
            if self.path.startswith('/api/export/'):
                run=load(self.path.rsplit('/',1)[-1])
                if run['status']!='approved': return self.reply(409,{'error':'尚未人工确认，不能导出。'})
                return self.reply(200,run['report']+f"\n\n人工确认人：{run['reviewer']}\n确认时间：{run['approved_at']}\n",'text/markdown; charset=utf-8')
            return self.reply(404,{'error':'页面不存在。'})
        except (ValueError,FileNotFoundError): return self.reply(404,{'error':'记录不存在。'})
    def do_POST(self):
        if self.headers.get('Origin') not in [None,f'http://{self.headers.get("Host")}']:
            return self.reply(403,{'error':'不接受跨来源请求。'})
        if self.headers.get('Content-Type','').split(';')[0]!='application/json':
            return self.reply(415,{'error':'请求须为JSON。'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<200000: raise ValueError('资料不能为空或超过200KB。')
            data=json.loads(self.rfile.read(length))
            if not isinstance(data,dict): raise ValueError('请求须为对象。')
            if self.path=='/api/sources': return self.reply(200,sources.fetch(STORE,data.get('provider')))
            if self.path in ['/api/run','/api/jobs']: sources.verify(STORE,data.get('facts'))
            if self.path=='/api/benchmarks/compare': return self.reply(200,comparison.compare(benchmark.get(STORE,data.get('baseline')),benchmark.get(STORE,data.get('candidate'))))
            if self.path=='/api/benchmarks': return self.reply(202,benchmark.submit(STORE,data))
            if self.path=='/api/benchmarks/rate': return self.reply(200,benchmark.rate(STORE,data))
            with LOCK:
                if self.path=='/api/jobs': return self.reply(202,jobs.submit(STORE,data))
                if self.path=='/api/jobs/retry': return self.reply(202,jobs.submit(STORE,{},data.get('id')))
                if self.path=='/api/run':
                    parent=None
                    if data.get('parent'):
                        parent=load(data['parent'])
                        if parent['round']>=2: raise ValueError('已达两次修订上限，请人工复核并新建任务。')
                    run=generate(data.get('topic'),data.get('facts'),assumptions=data.get('assumptions'),brief=data.get('brief'))
                    run.update(id=uuid4().hex,created_at=datetime.now(timezone.utc).isoformat(),parent=data.get('parent'),round=parent['round']+1 if parent else 0)
                    run.setdefault('task_id',parent['task_id'] if parent else run['id'])
                    save(run);return self.reply(200,run)
                if self.path=='/api/approve':
                    run=load(data.get('id'))
                    approve(run,data.get('reviewer'),data.get('confirmed'))
                    run['approved_at']=datetime.now(timezone.utc).isoformat();save(run);return self.reply(200,run)
            return self.reply(404,{'error':'接口不存在。'})
        except (ValueError,TypeError,FileNotFoundError) as e:
            return self.reply(400,{'error':str(e) if isinstance(e,ValueError) else '请求字段或记录无效。'})
        except Exception: return self.reply(500,{'error':'操作失败，已有记录保留。'})


if __name__=='__main__':
    jobs.recover(STORE)
    benchmark.recover(STORE)
    print('API comparison prototype: http://127.0.0.1:8767',flush=True)
    ThreadingHTTPServer(('127.0.0.1',8767),Handler).serve_forever()
