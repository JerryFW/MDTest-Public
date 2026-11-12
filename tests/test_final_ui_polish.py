import json
import unittest
from pathlib import Path

import mdtest
from mdtest.presentation import result_to_html


ROOT = Path(__file__).resolve().parents[1]


class FinalUiPolishTests(unittest.TestCase):
    def test_result_dashboard_has_integrated_product_shell(self):
        file = ROOT / "examples" / "data" / "synthetic_variance_relaxation_independent.csv"
        result = mdtest.manual(file, col=1, ts=10374, m=10, n="max", write_outputs=False, make_plots=False)
        html = result_to_html(result, level="guided")
        self.assertIn("mdtest-reportbar", html)
        self.assertIn("mdtest-metrics", html)
        self.assertIn("mdtest-notes", html)
        self.assertIn("structured scientific report", html)

    def test_primary_notebook_uses_direct_python_workbench(self):
        notebook = json.loads((ROOT / "MDTestWorkbench.ipynb").read_text(encoding="utf-8"))
        source = "\n".join("".join(cell.get("source", [])) for cell in notebook["cells"])
        self.assertIn("from mdtest.workbench import launch", source)
        self.assertIn("from mdtest.presentation import display_result", source)
        self.assertNotIn("subprocess", source)
        self.assertIn("Scientific analysis workspace", source)


if __name__ == "__main__":
    unittest.main()
