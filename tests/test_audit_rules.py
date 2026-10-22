import unittest

from audit_rules import can_reaudit, summarize_item_statuses


class AuditRulesTests(unittest.TestCase):
    def test_reaudit_requires_both_confirmations(self):
        self.assertFalse(can_reaudit(False, False))
        self.assertFalse(can_reaudit(True, False))
        self.assertFalse(can_reaudit(False, True))
        self.assertTrue(can_reaudit(True, True))

    def test_all_ok_items_produce_approved_stage_statuses(self):
        items = [
            {"Status": "OK", "Status Comercial": "OK"},
            {"Status": "OK", "Status Comercial": "OK"},
        ]
        self.assertEqual(summarize_item_statuses(items), ("OK", "OK"))

    def test_any_non_ok_item_makes_only_its_stage_pending(self):
        fiscal_pending = [
            {"Status": "DIVERGENTE", "Status Comercial": "OK"},
            {"Status": "OK", "Status Comercial": "OK"},
        ]
        commercial_pending = [
            {"Status": "OK", "Status Comercial": "PENDENTE - REVISÃO DE PREÇO"},
        ]
        self.assertEqual(
            summarize_item_statuses(fiscal_pending),
            ("PENDENTE/DIVERGENTE", "OK"),
        )
        self.assertEqual(
            summarize_item_statuses(commercial_pending),
            ("OK", "PENDENTE/DIVERGENTE"),
        )

    def test_empty_items_are_not_approved(self):
        self.assertEqual(
            summarize_item_statuses([]),
            ("PENDENTE/DIVERGENTE", "PENDENTE/DIVERGENTE"),
        )


if __name__ == "__main__":
    unittest.main()
