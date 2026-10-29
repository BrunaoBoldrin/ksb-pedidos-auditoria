import unittest


class SystemSettingsTests(unittest.TestCase):
    def settings_module(self):
        try:
            import system_settings
        except ModuleNotFoundError:
            self.fail("O módulo system_settings deve existir")
        return system_settings

    def test_missing_values_use_approved_defaults(self):
        module = self.settings_module()
        settings = module.normalize_system_settings({})
        self.assertEqual(settings.price_review_days, 90)
        self.assertEqual(settings.price_difference_tolerance, 0.01)
        self.assertEqual(settings.fiscal_difference_tolerance, 1.0)

    def test_valid_text_values_are_normalized_to_numeric_settings(self):
        module = self.settings_module()
        settings = module.normalize_system_settings({
            "price_review_days": "120",
            "price_difference_tolerance": "0.50",
            "fiscal_difference_tolerance": "2.75",
        })
        self.assertEqual(settings.price_review_days, 120)
        self.assertEqual(settings.price_difference_tolerance, 0.5)
        self.assertEqual(settings.fiscal_difference_tolerance, 2.75)

    def test_invalid_persisted_values_fall_back_independently(self):
        module = self.settings_module()
        settings = module.normalize_system_settings({
            "price_review_days": 0,
            "price_difference_tolerance": -1,
            "fiscal_difference_tolerance": "inválido",
        })
        self.assertEqual(settings.price_review_days, 90)
        self.assertEqual(settings.price_difference_tolerance, 0.01)
        self.assertEqual(settings.fiscal_difference_tolerance, 1.0)

    def test_explicit_settings_reject_values_outside_safe_limits(self):
        module = self.settings_module()
        with self.assertRaises(ValueError):
            module.SystemSettings(price_review_days=3651)
        with self.assertRaises(ValueError):
            module.SystemSettings(price_difference_tolerance=1_000_000.01)
        with self.assertRaises(ValueError):
            module.SystemSettings(fiscal_difference_tolerance=-0.01)

    def test_explicit_review_period_must_be_an_integer_not_boolean(self):
        module = self.settings_module()
        for invalid_value in (90.5, True):
            with self.subTest(invalid_value=invalid_value), self.assertRaises(ValueError):
                module.SystemSettings(price_review_days=invalid_value)


if __name__ == "__main__":
    unittest.main()
