"""Runs the JavaScript tests for web/assets/plan.js with Node.js, if Node is installed."""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@unittest.skipUnless(shutil.which("node"), "Node.js not installed: JS export/Bingo tests skipped")
class PlanJsTests(unittest.TestCase):
    def test_plan_js(self):
        r = subprocess.run(["node", str(ROOT / "tests" / "js" / "plan_test.js")], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("plan.js tests passed", r.stdout)


if __name__ == "__main__":
    unittest.main()
