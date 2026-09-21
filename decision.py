"""A decision brief, not an automatic endorsement of a model."""
from decimal import Decimal, InvalidOperation

def build(brief, facts, costs):
    if not isinstance(brief,dict):raise ValueError('选型需求须为对象。')
    normalized={}
    for key in ('scenario','requirements','acceptance'):
        value=brief.get(key,'')
        if not isinstance(value,str) or len(value)>2000:raise ValueError('选型需求每项最多2000字。')
        normalized[key]=value.strip()
    budget=brief.get('budget_usd','')
    if budget in ('',None):normalized['budget_usd']=None
    else:
        try:
            n=Decimal(str(budget))
            if isinstance(budget,bool) or not n.is_finite() or n<0 or n>10**12:raise ValueError()
        except (ValueError,InvalidOperation):raise ValueError('期间 Token 预算须为非负有限数字，或留空。')
        normalized['budget_usd']=str(n)
    rows=[]
    for provider,model in dict.fromkeys((f['provider'],f['model_id']) for f in facts):
        fs=[f for f in facts if (f['provider'],f['model_id'])==(provider,model)]
        estimates=[r for r in (costs or {}).get('rows',[]) if (r['provider'],r['model'])==(provider,model)]
        checks=[]
        for r in estimates:
            budget=normalized['budget_usd']
            verdict='未设预算' if budget is None else ('预算内' if Decimal(r['usd'])<=Decimal(budget) else '超出预算')
            checks.append(dict(usd=r['usd'],conditions=r['conditions'],evidence=r['evidence'],verdict=verdict,evidence_type=r['evidence_type']))
        rows.append(dict(provider=provider,model=model,budget_checks=checks,
            capability_refs=[f['fact_id'] for f in fs if f['dimension']=='capability'],
            measurement_refs=[f['fact_id'] for f in fs if f['evidence_type']=='measurement'],
            terms_refs=[f['fact_id'] for f in fs if f['dimension']=='terms']))
    return dict(brief=normalized,candidates=rows,status='待人工决策')

def markdown(d):
    b=d['brief'];lines=['\n\n## 选型决策简报（待人工决策）',
        '业务场景：'+(b['scenario'] or '待填写'),'必须满足：'+(b['requirements'] or '待填写'),
        '验收标准：'+(b['acceptance'] or '待填写'),
        '同估算期间 Token 预算（USD）：'+(b['budget_usd'] if b['budget_usd'] is not None else '未设置'),
        '预算内仅代表所填价格与调用假设下的 Token 费用合格；合成卡仅供演示。功能、效果和条款均需逐项核实，未自动评分或推荐。']
    for r in d['candidates']:
        lines.append(f"### {r['provider']} / {r['model']}")
        if not r['budget_checks']:lines.append('- 费用：无法判断，需补齐同口径价格与调用假设。')
        for c in r['budget_checks']:lines.append(f"- {c['verdict']}：{c['usd']} USD；{c['conditions']}；{c['evidence_type']}；依据 {', '.join(c['evidence'])}")
        for field,label in [('capability_refs','功能'),('measurement_refs','实测'),('terms_refs','条款')]:
            refs=r[field];lines.append(f"- {label}："+('已有资料 '+', '.join(refs)+'，内容与验收要求的匹配待人工核查。' if refs else '缺少资料，待补证据。'))
    lines+=['### 下一轮验证任务','1. 产品负责人确认业务场景、必需功能、预算期间与验收门槛。','2. 用相同且脱敏的业务测试集运行候选模型，记录模型版本、日期、实际 Token、耗时与错误。','3. 按预先约定的标准人工判定结果，保留失败案例及原始证据。','4. 复核价格、服务条款与业务效果，再记录候选选择、取舍理由及决策人。','当前报告确认仅表示资料审核完成，不代表已通过业务验收。']
    return '\n'.join(lines)
