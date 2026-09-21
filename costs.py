"""Deterministic token fees; estimates are not provider invoices."""
from decimal import Decimal, InvalidOperation
from itertools import combinations

def calculate(facts, assumptions):
    vals={}
    for key in ('requests','input_tokens','output_tokens'):
        try:
            raw=assumptions[key]
            n=Decimal(str(raw))
            if isinstance(raw,bool) or not n.is_finite() or n<0 or n>10**12 or n!=n.to_integral_value(): raise ValueError()
        except (KeyError,TypeError,InvalidOperation,ValueError):
            raise ValueError('调用量与每次输入／输出 token 必须为 0 至 10^12 的整数。')
        vals[key]=n
    groups={}
    for f in facts:
        if f.get('dimension') not in ('input_price','output_price'): continue
        key=tuple(f[k] for k in ('provider','model_id','conditions','evidence_type'))
        groups.setdefault(key,{})[f['dimension']]=f
    rows=[]; gaps=[]
    for (provider,model,conditions,kind), pair in groups.items():
        if len(pair)!=2:
            gaps.append(f'{provider}/{model}：同条件下缺少输入或输出价格，不估算。'); continue
        a,b=pair['input_price'],pair['output_price']
        pi,po=Decimal(str(a['value'])),Decimal(str(b['value']))
        fee=vals['requests']*(vals['input_tokens']*pi+vals['output_tokens']*po)/Decimal(1000000)
        rows.append(dict(provider=provider,model=model,conditions=conditions,evidence_type=kind,usd=format(fee,'f'),input_price=str(pi),output_price=str(po),evidence=[a['fact_id'],b['fact_id']]))
    thresholds=[]
    for a,b in combinations(rows,2):
        if (a['conditions'],a['evidence_type'])!=(b['conditions'],b['evidence_type']): continue
        numerator=Decimal(b['input_price'])-Decimal(a['input_price'])
        denominator=Decimal(a['output_price'])-Decimal(b['output_price'])
        if denominator and numerator/denominator>=0:
            thresholds.append(dict(a=a['model'],b=b['model'],output_per_input=str(numerator/denominator),evidence=a['evidence']+b['evidence']))
    return dict(assumptions={k:int(v) for k,v in vals.items()},rows=rows,gaps=gaps,thresholds=thresholds)

def markdown(result):
    a=result['assumptions']
    lines=['\n\n## 程序计算：Token 费用估算',f"所选期间调用 {a['requests']} 次；每次输入 {a['input_tokens']}、输出 {a['output_tokens']} tokens。",'公式：调用量 ×（输入 tokens × 输入单价＋输出 tokens × 输出单价）÷ 1,000,000。', '仅计算所填口径的 token 费用，不含税、工具费及其他费用。相同文本在不同模型的 token 数可能不同；此处假设 token 数相同，不代表相同任务效果。']
    for r in result['rows']:
        lines.append(f"- {r['provider']} / {r['model']}：{r['usd']} USD；{r['conditions']}；{r['evidence_type']}；依据 {', '.join(r['evidence'])}")
    lines+=result['gaps']
    lines.append('以下为条件文字和证据类型相同的价格对；仍需人工确认计费口径确实可比。输入 tokens > 0 时，两模型费用相等的输出／输入 token 比：')
    for t in result['thresholds']: lines.append(f"- {t['a']} vs {t['b']}：{t['output_per_input']}；依据 {', '.join(t['evidence'])}")
    return '\n'.join(lines)
