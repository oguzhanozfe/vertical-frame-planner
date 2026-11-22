import json
from pathlib import Path
import unittest

from project import analyze


def example():
    return json.loads(Path(__file__).with_name("example.json").read_text(encoding="utf-8"))


class ProjectTests(unittest.TestCase):
    def test_safe_and_impossible_shots(self):
        result = analyze(example())
        self.assertEqual(result["metrics"]["Need reframing"], 1)
        row = result["rows"][0]
        self.assertEqual(row["Width (px)"] * 16, row["Height (px)"] * 9)
        self.assertIn("Package", result["rows"][1]["Outside safe area"])

    def test_margin_at_source_edge(self):
        data = example()
        subject = data["shots"][0]["subjects"][0]
        subject["x"] = 0
        self.assertEqual(analyze(data)["rows"][0]["Outside safe area"], "Dial")
        data["safe_margin"] = 0
        self.assertEqual(analyze(data)["rows"][0]["Outside safe area"], "None")

    def test_clamps_crop_to_image(self):
        row = analyze(example())["rows"][-1]
        self.assertLessEqual(row["Left (px)"] + row["Width (px)"], 1920)
        self.assertLessEqual(row["Top (px)"] + row["Height (px)"], 1080)

    def test_out_of_bounds_box(self):
        data = example()
        data["shots"][0]["subjects"][0]["width"] = 2000
        with self.assertRaises(ValueError):
            analyze(data)


if __name__ == "__main__":
    unittest.main()
