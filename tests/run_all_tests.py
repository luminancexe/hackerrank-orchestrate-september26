import os
import sys
import time
import unittest

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

TEST_MODULES = [
    "tests.test_ingestion",
    "tests.test_cashflow",
    "tests.test_safe_amount",
    "tests.test_payment_plans",
    "tests.test_spending_changes",
    "tests.test_ranking",
    "tests.test_messages_and_images",
    "tests.test_properties_and_fuzz",
    "tests.test_hardcoding_audit",
    "tests.test_end_to_end"
]

def run_all():
    print("=" * 70)
    print("BUY OR WAIT? — COMPREHENSIVE TEST SUITE MASTER RUNNER")
    print("=" * 70)

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    for mod_name in TEST_MODULES:
        try:
            mod_suite = loader.loadTestsFromName(mod_name)
            suite.addTests(mod_suite)
        except Exception as e:
            print(f"Error loading {mod_name}: {e}")

    start_time = time.time()
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    elapsed = time.time() - start_time

    print("\n" + "=" * 70)
    print("TEST SUITE SUMMARY:")
    print(f"Total Tests Executed: {result.testsRun}")
    print(f"Passed:               {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures:             {len(result.failures)}")
    print(f"Errors:               {len(result.errors)}")
    print(f"Total Time:           {elapsed:.2f}s")
    print("=" * 70)

    if result.wasSuccessful():
        print("ALL TESTS PASSED SUCCESSFULLY! (100% PASS RATE)")
        return 0
    else:
        print("SOME TESTS FAILED.")
        return 1

if __name__ == "__main__":
    sys.exit(run_all())
