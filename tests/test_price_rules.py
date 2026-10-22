import unittest
from datetime import date

from price_rules import add_calendar_months, is_price_outdated, parse_review_date


class PriceRulesTests(unittest.TestCase):
    def test_accepts_supported_review_date_formats(self):
        expected = date(2026, 7, 22)
        for value in ("2026-07-22", "22/07/2026", "22.07.2026"):
            with self.subTest(value=value):
                self.assertEqual(parse_review_date(value), expected)

    def test_missing_or_invalid_date_is_outdated(self):
        for value in (None, "", "data inválida", "31/02/2026"):
            with self.subTest(value=value):
                self.assertTrue(is_price_outdated(value, date(2026, 10, 22)))

    def test_price_is_valid_on_exact_three_month_boundary(self):
        self.assertFalse(is_price_outdated("2026-07-22", date(2026, 10, 22)))

    def test_price_is_outdated_on_day_after_boundary(self):
        self.assertTrue(is_price_outdated("2026-07-22", date(2026, 10, 23)))

    def test_calendar_month_addition_clamps_end_of_month(self):
        self.assertEqual(add_calendar_months(date(2026, 1, 31), 3), date(2026, 4, 30))


if __name__ == "__main__":
    unittest.main()
