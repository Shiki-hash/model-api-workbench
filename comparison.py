"""Descriptive paired comparison, never a causal improvement claim."""
import benchmark

def compare(a,b):
    if a['id']==b['id']:raise ValueError('请选择两个不同批次。')
    if any(x['status'] not in ('completed','interrupted') for x in (a,b)):raise ValueError('请等待两个批次结束。')
    if a['cases']!=b['cases']:raise ValueError('案例、顺序、来源或评分标准不同，不能作为同集对照。')
    if a['mode']!=b['mode']:raise ValueError('固定演示不能与真实 API 调用作效果对照。')
    ar={r['case_id']:r for r in a['ratings']};br={r['case_id']:r for r in b['ratings']}
    common=sorted(ar.keys()&br.keys())
    paired=[dict(case_id=k,baseline=ar[k]['verdict'],candidate=br[k]['verdict'],baseline_reviewer=ar[k]['reviewer'],candidate_reviewer=br[k]['reviewer']) for k in common]
    delta=(sum(br[k]['verdict']=='pass' for k in common)-sum(ar[k]['verdict']=='pass' for k in common))/len(common)*100 if common else None
    notes=['这是描述性对照，不证明版本修改导致效果提升；小样本不可外推。','耗时均值只统计各批完整回答，成功样本集合不同时不能直接解释为速度提升。']
    if not a.get('request_settings') or not b.get('request_settings'):notes.append('旧批次生成参数未完整记录，无法确认调用条件一致。')
    elif a['request_settings']!=b['request_settings']:notes.append('生成参数不同，不能把差异仅归因于提示词或模型。')
    if a.get('runner_version')!=b.get('runner_version'):notes.append('执行器版本不同，需要核查实现变化。')
    if a['model']!=b['model']:notes.append('配置模型不同，属于对照差异。')
    if a.get('prompt_sha256')!=b.get('prompt_sha256'):notes.append('系统提示词发生变化，属于干预差异。')
    if not common:notes.append('尚无双方均已人工评分的案例，不计算通过率差值。')
    if any(ar[k]['reviewer']!=br[k]['reviewer'] for k in common):notes.append('部分配对评分人不同，需核对评分一致性。')
    if any(c['origin']=='synthetic' for c in a['cases']):notes.append('包含合成输入，不代表真实用户使用效果。')
    return dict(baseline=dict(id=a['id'],model=a['model'],summary=benchmark.summary(a)),candidate=dict(id=b['id'],model=b['model'],summary=benchmark.summary(b)),paired_count=len(common),paired_coverage=len(common)/len(a['cases']),pass_delta_percentage_points=delta,paired=paired,notes=notes)
