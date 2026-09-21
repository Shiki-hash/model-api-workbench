import unittest
from engine import generate
from server import sample

class DecisionTests(unittest.TestCase):
    def run_report(self,budget='29',facts=None):
        return generate('选型验收',facts or sample(),assumptions=dict(requests=10000,input_tokens=1000,output_tokens=500),brief=dict(scenario='答疑草稿',requirements='中文引用',acceptance='待组织测试',budget_usd=budget))
    def test_budget_boundary(self):
        r=self.run_report()
        self.assertEqual([c['budget_checks'][0]['verdict'] for c in r['decision']['candidates']],['超出预算','预算内','预算内'])
        self.assertEqual(r['status'],'awaiting_human')
        self.assertIn('合成卡仅供演示',r['report'])
    def test_no_budget(self):
        self.assertEqual(self.run_report('')['decision']['candidates'][0]['budget_checks'][0]['verdict'],'未设预算')
    def test_zero_budget(self):self.assertEqual(self.run_report('0')['decision']['candidates'][0]['budget_checks'][0]['verdict'],'超出预算')
    def test_invalid_budget(self):
        for x in ('NaN','Infinity',-1,True,{}):
            with self.subTest(x=x),self.assertRaises(ValueError):self.run_report(x)
    def test_missing_prices_retains_candidate(self):
        r=self.run_report(facts=sample()[:1]);c=r['decision']['candidates'][0]
        self.assertEqual(c['budget_checks'],[]);self.assertEqual(c['measurement_refs'],[])
        self.assertIn('无法判断',r['report'])
    def test_multiple_conditions_not_collapsed(self):
        f=sample()[:2];more=[dict(x,fact_id=x['fact_id']+'x',conditions='另一个口径',value=100) for x in f]
        c=self.run_report(facts=f+more)['decision']['candidates'][0]
        self.assertEqual(len(c['budget_checks']),2)
    def test_bad_brief(self):
        with self.assertRaises(ValueError):generate('测试',sample(),brief={'requirements':[]})
    def test_evidence_is_not_acceptance(self):
        f=sample();f.append(dict(f[0],fact_id='CAP',dimension='capability',value='支持中文'))
        r=self.run_report(facts=f)
        self.assertEqual(r['decision']['candidates'][0]['capability_refs'],['CAP'])
        self.assertIn('匹配待人工核查',r['report'])
