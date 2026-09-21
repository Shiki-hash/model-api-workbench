"""Original offline evidence comparison prototype; no upstream code copied."""
import json
import math
from datetime import date
from urllib.parse import urlparse

VERSION = 'decision-brief-0.5'
import costs
import decision


def review(facts, today=None):
    today = today or date.today()
    issues, seen, groups = [], set(), {}
    if not isinstance(facts, list) or not 1 <= len(facts) <= 60:
        return ['请提供1至60条事实卡。']
    required = ['fact_id','provider','model_id','dimension','unit','conditions',
                'source_url','source_excerpt','retrieved_at','evidence_type']
    for i, f in enumerate(facts):
        tag = f'第{i+1}条'
        if not isinstance(f, dict):
            issues.append(f'{tag}不是事实对象。'); continue
        if any(not isinstance(f.get(k), str) or not f[k].strip() for k in required):
            issues.append(f'{tag}缺少必要字段或字段格式错误。'); continue
        tag = f['fact_id']
        if tag in seen: issues.append(f'{tag}编号重复。')
        seen.add(tag)
        if f['evidence_type'] not in ['synthetic','official_claim','measurement']:
            issues.append(f'{tag}证据类型无效，推断不能作为事实输入。')
        url = urlparse(f['source_url'])
        if url.scheme != 'https' or not url.hostname:
            issues.append(f'{tag}来源必须为完整HTTPS链接。')
        try:
            age = (today-date.fromisoformat(f['retrieved_at'])).days
            if age < 0 or age > 30: issues.append(f'{tag}采集日期在未来或超过30天，请重新核查。')
        except ValueError: issues.append(f'{tag}日期格式应为YYYY-MM-DD。')
        v = f.get('value')
        if v is None or isinstance(v,bool) or not isinstance(v,(str,int,float)) or (isinstance(v,str) and not v.strip()):
            issues.append(f'{tag}缺少有效事实值；不能补造。')
        if isinstance(v,float) and not math.isfinite(v): issues.append(f'{tag}数值必须有限。')
        if f['dimension'] in ['input_price','output_price']:
            if f['unit'] != 'USD/1M tokens': issues.append(f'{tag}价格单位须统一为USD/1M tokens，其他币种需人工换算并保留依据。')
            if isinstance(v,bool) or not isinstance(v,(int,float)) or v < 0:
                issues.append(f'{tag}价格须为非负数字。')
        key = tuple(f[k] for k in ['provider','model_id','dimension','conditions','evidence_type'])
        value = json.dumps([v,f['unit']],ensure_ascii=False)
        if key in groups and groups[key] != value: issues.append(f'{tag}同口径资料冲突，请核查后再生成。')
        groups[key] = value
    return issues


def make_report(topic, facts, issues):
    lines = ['# 模型 API 资料对比', '', f'任务：{topic}', '',
             '运行方式：离线规则与模板；未调用大模型，未访问来源网站。',
             '示例卡含 synthetic 时为合成演示，不能作为真实价格或选型结论。', '',
             '## 审核结果', '', *(('- '+x for x in issues) if issues else ['结构与口径检查通过；原文真实性与适用性仍需人工核查。']), '', '## 事实卡', '']
    for f in facts:
        if not isinstance(f,dict): continue
        lines += [f"### {f.get('fact_id','未编号')} · {f.get('provider','')} / {f.get('model_id','')}",
                  f"维度：{f.get('dimension','')}；值：{f.get('value','未提供')}；单位：{f.get('unit','')}",
                  f"条件：{f.get('conditions','')}；证据类型：{f.get('evidence_type','')}",
                  f"来源：{f.get('source_url','')}；采集日期：{f.get('retrieved_at','')}",
                  f"采集快照：{f.get('source_snapshot_id','未关联（手动来源）')}；可通过 /api/sources/快照ID 回查正文",
                  f"提供的原文摘录：{f.get('source_excerpt','')}", '']
    lines += ['## 比较边界', '', '按模型ID、维度、单位及计费条件逐项比较。未提供的性能、延迟、条款与真实任务效果均待核查。',
              '费用仅按用户填写的 token 假设计算；不代表综合性能排名或真实账单。']
    return '\n'.join(lines)


def generate(topic, facts, reviewer=None, assumptions=None, brief=None):
    if not isinstance(topic,str) or not topic.strip() or len(topic)>500:
        raise ValueError('请填写500字以内的任务。')
    if not isinstance(facts,list) or len(facts)>60: raise ValueError('事实卡必须为最多60条的列表。')
    try:
        issues = (reviewer or review)(facts)
        if not isinstance(issues,list) or any(not isinstance(x,str) for x in issues):
            raise ValueError('invalid review result')
    except Exception:
        issues = ['审核执行失败；保留草稿，不能确认导出。']
    result = dict(topic=topic,facts=facts,issues=issues,version=VERSION,
                status='blocked' if issues else 'awaiting_human',
                report=make_report(topic,facts,issues))
    if assumptions is not None:
        result["assumptions"]=assumptions
        if not issues:
            result["costs"]=costs.calculate(facts, assumptions)
            result["report"]+=costs.markdown(result["costs"])
    if brief is not None and not issues:
        result["decision"]=decision.build(brief,facts,result.get("costs"))
        result["brief"]=result["decision"]["brief"]
        result["report"]+=decision.markdown(result["decision"])
    return result


def approve(run, reviewer_name, confirmed):
    if run['status'] != 'awaiting_human' or run['issues']:
        raise ValueError('仅检查通过且待人工确认的版本可以确认。')
    if confirmed is not True or not isinstance(reviewer_name,str) or not reviewer_name.strip() or len(reviewer_name)>60:
        raise ValueError('请填写审核人，并确认已核对来源、日期与适用条件。')
    run['status']='approved'; run['reviewer']=reviewer_name.strip()
    return run
