import unittest
from datetime import date
from inspect import signature

from price_rules import is_price_outdated, parse_review_date


class PriceRulesTests(unittest.TestCase):
    def assert_configurable_period_supported(self):
        self.assertIn("max_age_days", signature(is_price_outdated).parameters)

    def test_accepts_supported_review_date_formats(self):
        expected = date(2026, 7, 22)
        for value in ("2026-07-22", "22/07/2026", "22.07.2026"):
            with self.subTest(value=value):
                self.assertEqual(parse_review_date(value), expected)

    def test_missing_or_invalid_date_is_outdated(self):
        for value in (None, "", "data inválida", "31/02/2026"):
            with self.subTest(value=value):
                self.assertTrue(is_price_outdated(value, date(2026, 10, 22)))

    def test_price_is_valid_on_exact_configured_day_boundary(self):
        self.assert_configurable_period_supported()
        self.assertFalse(is_price_outdated("2026-01-31", date(2026, 5, 1), max_age_days=90))

    def test_price_is_outdated_on_day_after_configured_boundary(self):
        self.assert_configurable_period_supported()
        self.assertTrue(is_price_outdated("2026-01-31", date(2026, 5, 2), max_age_days=90))

    def test_custom_review_period_changes_expiration_date(self):
        self.assert_configurable_period_supported()
        self.assertFalse(is_price_outdated("2026-10-01", date(2026, 10, 31), max_age_days=30))
        self.assertTrue(is_price_outdated("2026-10-01", date(2026, 11, 1), max_age_days=30))


if __name__ == "__main__":
    unittest.main()
