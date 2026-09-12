import os
import re
import sys
import unittest

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

class TestHardcodingAudit(unittest.TestCase):
    def test_25_no_request_id_hardcoding_in_code_directory(self):
        code_dir = os.path.join(repo_root, "code")
        self.assertTrue(os.path.exists(code_dir), "code/ directory must exist")

        forbidden_patterns = [
            (r'request_\d+', "Specific request ID pattern like request_01, request_25"),
            (r'user_\d+', "Specific user ID pattern like user_01, user_100"),
            (r'sample_requests\.csv', "Production code must not read sample_requests.csv for predictions"),
        ]

        py_files = []
        for root, _, files in os.walk(code_dir):
            for file in files:
                if file.endswith(".py"):
                    # Exclude evaluation harness which legitimately scores against sample_requests.csv
                    rel_path = os.path.relpath(os.path.join(root, file), code_dir)
                    if "evaluation" in rel_path.split(os.sep):
                        continue
                    py_files.append(os.path.join(root, file))

        self.assertGreater(len(py_files), 0, "Found no Python files in code/")

        violations = []
        for file_path in py_files:
            rel_name = os.path.relpath(file_path, repo_root)
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            for pattern, desc in forbidden_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    violations.append(f"File {rel_name} matched forbidden pattern '{pattern}' ({desc}): {matches[:5]}")

        self.assertEqual(len(violations), 0, "\n".join(violations))

if __name__ == "__main__":
    unittest.main()
