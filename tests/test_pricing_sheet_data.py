import unittest
from datetime import date

from pricing_sheet_data import sheet_rows, composition_from_rows


class SheetDataTests(unittest.TestCase):
    def catalog(self):
        base=dict(id=1,code='PARAFUSO',description='Parafuso teste',unit='UN',price='10.123456789012',factor='1',active=True,version=2,reviewed_on='2026-11-01')
        return dict(component=[base],material=[],process=[],service=[])

    def test_prices_remain_shared_proposals_while_times_and_quantities_belong_to_sheet(self):
        catalog=self.catalog()
        data=dict(lines=[dict(kind='component',base_id=1,quantity='2',consumption='1',unit='UN')])
        rows=sheet_rows(data,catalog)
        rows['component'][0]['Preço (R$)']='13.123456789012'
        rows['component'][0]['Quantidade']=3
        lines,proposals=composition_from_rows(rows,catalog,date(2026,11,6))
        self.assertEqual(lines[0]['quantity'],'3')
        self.assertNotIn('price',lines[0])
        self.assertEqual(proposals,[dict(kind='component',base_id=1,price='13.123456789012',version=2,reviewed_on='2026-11-06')])
        self.assertEqual(catalog['component'][0]['price'],'10.123456789012')

    def test_repeated_base_cannot_have_two_different_proposed_prices(self):
        catalog=self.catalog()
        data=dict(lines=[dict(kind='component',base_id=1,quantity='1',consumption='1',unit='UN')]*2)
        rows=sheet_rows(data,catalog)
        rows['component'][0]['Preço (R$)']='13';rows['component'][1]['Preço (R$)']='14'
        with self.assertRaises(ValueError):composition_from_rows(rows,catalog,date(2026,11,6))

    def test_person_count_round_trip_accepts_decimal_representation_without_truncation(self):
        catalog=self.catalog();catalog['process']=catalog.pop('component');catalog['component']=[]
        data=dict(lines=[dict(kind='process',base_id=1,people='1.0',minutes='10')])
        self.assertEqual(sheet_rows(data,catalog)['process'][0]['Pessoas'],1)

    def test_changing_base_alone_never_proposes_old_price_for_new_base(self):
        catalog=self.catalog()
        catalog['component'].append(dict(catalog['component'][0],id=2,code='OUTRO',price='100',version=5))
        rows=sheet_rows(dict(lines=[dict(kind='component',base_id=1)]),catalog)
        rows['component'][0]['Base']='OUTRO — Parafuso teste'
        lines,proposals=composition_from_rows(rows,catalog,date(2026,11,6))
        self.assertEqual(lines[0]['base_id'],2)
        self.assertEqual(proposals,[])

    def test_reopening_proposed_price_keeps_original_cost_version(self):
        catalog=self.catalog();catalog['component'][0]['price']='100'
        proposed=[dict(kind='component',base_id=1,price='80',version=1,reviewed_on='2026-11-01')]
        rows=sheet_rows(dict(lines=[dict(kind='component',base_id=1)],proposed_prices=proposed),catalog)
        _,proposals=composition_from_rows(rows,catalog,date(2026,11,6))
        self.assertEqual(proposals[0]['price'],'80')
        self.assertEqual(proposals[0]['version'],1)
