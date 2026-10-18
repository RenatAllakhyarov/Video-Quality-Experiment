import unittest

from video_quality.core import contrast_expression, gamma_expression, preprocessing_filter


class CoreTests(unittest.TestCase):
    def test_gamma_expression_rejects_invalid_value(self):
        with self.assertRaises(ValueError):
            gamma_expression(0)


    def test_contrast_expression_rejects_constant_range(self):
        with self.assertRaises(ValueError):
            contrast_expression(10, 10)


    def test_filters_are_deterministic_and_explicit(self):
        self.assertIn("pow(val/255", preprocessing_filter({"kind": "gamma", "gamma": 1.0}))
        self.assertNotIn("x_min", preprocessing_filter({"kind": "contrast", "x_min": 16, "x_max": 235}))


if __name__ == "__main__":
    unittest.main()
