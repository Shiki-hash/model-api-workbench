import copy
import unittest
from datetime import date,timedelta
from engine import generate,approve,review
from server import sample

class Acceptance(unittest.TestCase):
    def setUp(self):self.f=sample()
    def test_valid_requires_human(self):self.assertEqual(generate('任务',self.f)['status'],'awaiting_human')
    def test_missing_source(self):self.f[0]['source_url']='';self.assertTrue(review(self.f))
    def test_missing_price(self):self.f[0]['value']=None;self.assertTrue(review(self.f))
    def test_currency_mismatch(self):self.f[0]['unit']='CNY/1K tokens';self.assertTrue(review(self.f))
    def test_conflict(self):
        f=copy.deepcopy(self.f[0]);f['fact_id']='conflict';f['value']=90;self.f.append(f);self.assertTrue(review(self.f))
    def test_stale(self):self.f[0]['retrieved_at']=(date.today()-timedelta(days=31)).isoformat();self.assertTrue(review(self.f))
    def test_future(self):self.f[0]['retrieved_at']=(date.today()+timedelta(days=1)).isoformat();self.assertTrue(review(self.f))
    def test_timeout_blocks_preserves_draft(self):
        def timeout(f):raise TimeoutError()
        r=generate('任务',self.f,timeout);self.assertEqual(r['status'],'blocked');self.assertIn('S1',r['report'])
    def test_bad_review_blocks(self):self.assertEqual(generate('任务',self.f,lambda f:None)['status'],'blocked')
    def test_blocked_cannot_approve(self):
        self.f[0]['value']=None
        with self.assertRaises(ValueError):approve(generate('任务',self.f),'tester',True)
    def test_attestation_required(self):
        with self.assertRaises(ValueError):approve(generate('任务',self.f),'tester',False)
    def test_fixed_data_rechecked(self):
        self.f[0]['value']=None;old=generate('任务',copy.deepcopy(self.f));self.f[0]['value']=1
        new=generate('任务',self.f);approve(new,'offline tester',True)
        self.assertEqual(old['status'],'blocked');self.assertEqual(new['status'],'approved')

if __name__=='__main__':unittest.main()

