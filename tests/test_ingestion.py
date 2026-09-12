import os
import sys
import unittest

# Ensure repo root is in sys.path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from code.ingestion import DatasetLoader
from code.resolver import InformationResolver

class TestIngestion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.loader = DatasetLoader(data_dir="dataset")
        cls.loader.load_all()
        cls.resolver = InformationResolver()
        cls.resolver.resolve_image_events(cls.loader)

    def test_01_row_counts(self):
        eval_requests = self.loader.load_requests("requests.csv")
        self.assertEqual(len(eval_requests), 250, f"Expected 250 eval requests, got {len(eval_requests)}")
        
        samples = self.loader.load_requests("sample_requests.csv")
        self.assertEqual(len(samples), 25, f"Expected 25 sample requests, got {len(samples)}")
        
        self.assertEqual(len(self.loader.profiles), 275, f"Expected 275 profiles, got {len(self.loader.profiles)}")
        
        total_events = sum(len(evs) for evs in self.loader.events_by_user.values())
        self.assertEqual(total_events, 25342, f"Expected 25342 events, got {total_events}")
        
        total_opts = sum(len(opts) for opts in self.loader.payment_options.values())
        self.assertEqual(total_opts, 790, f"Expected 790 payment options, got {total_opts}")
        
        self.assertEqual(len(self.loader.exchange_rates), 134, f"Expected 134 exchange rates, got {len(self.loader.exchange_rates)}")
        
        total_msgs = sum(len(msgs) for msgs in self.loader.messages_by_user.values())
        self.assertEqual(total_msgs, 215, f"Expected 215 messages, got {total_msgs}")
        
        self.assertEqual(len(self.loader.image_mappings), 16, f"Expected 16 image mappings, got {len(self.loader.image_mappings)}")

    def test_02_referential_integrity(self):
        eval_requests = self.loader.load_requests("requests.csv")
        sample_requests = self.loader.load_requests("sample_requests.csv")
        all_requests = eval_requests + sample_requests
        req_ids = {r.request_id for r in all_requests}

        for r in all_requests:
            self.assertIn(r.user_id, self.loader.profiles, f"Request {r.request_id} has invalid user_id {r.user_id}")

        for uid, evs in self.loader.events_by_user.items():
            self.assertIn(uid, self.loader.profiles, f"Event collection has unknown user_id {uid}")
            for e in evs:
                self.assertEqual(e.user_id, uid, f"Event {e.event_id} user_id {e.user_id} != {uid}")

        for rid, opts in self.loader.payment_options.items():
            self.assertIn(rid, req_ids, f"Payment option references unknown request {rid}")
            for opt in opts:
                self.assertEqual(opt.request_id, rid)

        all_event_ids = {e.event_id for evs in self.loader.events_by_user.values() for e in evs}
        for uid, msgs in self.loader.messages_by_user.items():
            self.assertIn(uid, self.loader.profiles, f"Message user {uid} not in profiles")
            for m in msgs:
                self.assertEqual(m.user_id, uid)
                if m.request_id:
                    self.assertIn(m.request_id, req_ids)
                if m.related_event_id:
                    self.assertIn(m.related_event_id, all_event_ids)

        for img in self.loader.image_mappings:
            self.assertIn(img.user_id, self.loader.profiles)
            if img.request_id:
                self.assertIn(img.request_id, req_ids)
            if img.related_event_id:
                self.assertIn(img.related_event_id, all_event_ids)

    def test_03_missing_amounts_resolution(self):
        all_events = {e.event_id: e for evs in self.loader.events_by_user.values() for e in evs}
        self.assertEqual(len(self.loader.image_mappings), 16)
        
        for img in self.loader.image_mappings:
            if img.related_event_id:
                e = all_events[img.related_event_id]
                self.assertIsNotNone(e.normalized_amount, f"Event {e.event_id} normalized_amount is None")
                self.assertGreater(e.normalized_amount, 0)
            
            img_file = os.path.join("dataset", "media", "images", f"{img.image_id}.png")
            self.assertTrue(os.path.exists(img_file), f"Image file {img_file} not found")

    def test_04_foreign_currency_conversion(self):
        for uid, evs in self.loader.events_by_user.items():
            p = self.loader.profiles[uid]
            home = p.home_currency
            for e in evs:
                if e.currency != home and e.amount is not None:
                    self.assertIsNotNone(e.normalized_amount, f"Event {e.event_id} in {e.currency} not converted")
                    rate = self.loader.get_exchange_rate(e.settlement_date, e.currency, home)
                    self.assertIsNotNone(rate, f"Missing rate for {e.currency}->{home} on {e.settlement_date}")
                    expected = round(e.amount * rate, 2)
                    self.assertLessEqual(abs(e.normalized_amount - expected), 0.05)

if __name__ == "__main__":
    unittest.main()
