import unittest
from datetime import date
from decimal import Decimal

from pricing_analysis import evaluate_price
from system_settings import SystemSettings


class CommercialPriceTests(unittest.TestCase):
    def reference(self,**changes):
        row=dict(state='ACTIVE',price='157.14',revision=2,reviewed_on='2026-11-01',unit='UN',snapshot_id=15)
        row.update(changes);return row

    def test_difference_total_and_revision_are_explained(self):
        result=evaluate_price('142.86','10','PEÇ',self.reference(),date(2026,11,6),SystemSettings())
        self.assertNotEqual(result['status'],'OK')
        self.assertEqual(result['difference'],Decimal('-14.28'))
        self.assertEqual(result['total_difference'],Decimal('-142.80'))
        self.assertIn('2',result['diagnosis'])

    def test_missing_sheet_does_not_accept_old_manual_price(self):
        result=evaluate_price('100','1','UN',dict(state='MISSING',price='100'),date(2026,11,6),SystemSettings())
        self.assertIn('FOLHA',result['status'])
        self.assertIsNone(result['price'])

    def test_tolerance_boundary_is_inclusive(self):
        for order,expected in [('157.13','OK'),('157.12','PENDENTE - PREÇO DIVERGENTE')]:
            with self.subTest(order=order):
                result=evaluate_price(order,'1','UN',self.reference(),date(2026,11,6),SystemSettings())
                self.assertEqual(result['status'],expected)

    def test_expired_revision_does_not_hide_price_difference(self):
        result=evaluate_price('140','1','UN',self.reference(reviewed_on='2020-01-01'),date(2026,11,6),SystemSettings())
        self.assertIn('REVISÃO',result['diagnosis'])
        self.assertIn('DIVERGENTE',result['diagnosis'])

    def test_unit_mismatch_and_changed_fiscal_context_block_acceptance(self):
        for unit,ref in [('KG',self.reference()),('UN',self.reference(state='FISCAL_CHANGED'))]:
            result=evaluate_price('157.14','1',unit,ref,date(2026,11,6),SystemSettings())
            self.assertNotEqual(result['status'],'OK')


if __name__=='__main__':unittest.main()
