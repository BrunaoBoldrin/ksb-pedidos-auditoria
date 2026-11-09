import unittest
from decimal import Decimal

from pricing_calculator import calculate_sheet, PricingError


def base(price='120', unit='H', **kwargs):
    return dict(price=price, unit=unit, factor='1', reviewed_on='2026-11-06',
                active=True, code='TEST', description='Teste', **kwargs)


def sheet(lines, **kwargs):
    result = dict(lines=lines, margin='0', taxes='0', commission='0', efficiency='1',
                  rounding='CENT', basis='NET', confirmed=True,
                  reviewed_on='2026-11-06', tool_cost='0')
    result.update(kwargs)
    return result


class CalculatorTests(unittest.TestCase):
    def test_tooling_uses_explicit_amortization_quantity_without_double_legacy_cost(self):
        row=dict(kind='component',base_id=1,quantity='1',consumption='1',unit='UN')
        data=sheet([row],tool_cost='999',tooling=[dict(description='Matriz',annual_quantity='1000',cost='600',amortization_quantity='200')])
        result=calculate_sheet(data,{('component',1):base('10','UN')})
        self.assertEqual(result.cost,Decimal('13'))
        self.assertEqual(result.breakdown['tool'],Decimal('3'))
        data['tooling'][0]['amortization_quantity']='0'
        with self.assertRaises(PricingError):calculate_sheet(data,{('component',1):base('10','UN')})

    def test_time_efficiency_and_people_are_applied_once(self):
        row = dict(kind='process', base_id=1, minutes='6', hours='0', people=2)
        result = calculate_sheet(sheet([row], efficiency='0.65'),
                                 {('process', 1): base(per_person=True)})
        self.assertAlmostEqual(result.cost, Decimal('36.92307692307692307692307692'))
        result = calculate_sheet(sheet([row], efficiency='0.65'),
                                 {('process', 1): base(per_person=False)})
        self.assertAlmostEqual(result.cost, Decimal('18.46153846153846153846153846'))

    def test_blank_consumption_efficiency_and_whole_real_rounding(self):
        rows = [dict(kind='material', base_id=1, mode='BLANK', quantity='1',
                     blank_length='500', blank_width='400', piece_length='370', piece_width='340')]
        bases = {('material', 1): base('10.01', 'KG', kg_m2='12.5')}
        bases[('material', 1)]['factor'] = '0.8'
        for i, (minutes, rate) in enumerate([('30','60'),('10','60'),('2','90'),('5','120')], 2):
            rows.append(dict(kind='process', base_id=i, hours='0', minutes=minutes, people=1))
            bases[('process', i)] = base(rate, per_person=True)
        result = calculate_sheet(sheet(rows, efficiency='0.5', margin='0.2',
                                       taxes='0.1', rounding='UP_REAL'), bases)
        self.assertAlmostEqual(result.cost, Decimal('126.02'))
        self.assertEqual(result.gross_price, Decimal('181.00'))

    def test_bar_conversion_counts_two_components(self):
        rows = [dict(kind='component', base_id=1, quantity='2', consumption='880', unit='MM')]
        result = calculate_sheet(sheet(rows), {('component',1):base('8','BAR', length_mm='6000')})
        self.assertAlmostEqual(result.cost, Decimal('2.346666666666666666666666667'))

    def test_shared_purchase_factor_is_not_applied_twice(self):
        row = dict(kind='component', base_id=1, quantity='2', consumption='1', unit='UN')
        result = calculate_sheet(sheet([row], margin='0.2', taxes='0.3'),
                                 {('component',1):base('100','UN')})
        self.assertEqual(result.cost, Decimal('200'))
        self.assertEqual(result.gross_price, Decimal('400.00'))

    def test_gross_to_net_uses_confirmed_fiscal_divisor(self):
        row = dict(kind='component',base_id=1,quantity='1',consumption='1',unit='UN')
        result=calculate_sheet(sheet([row],basis='GROSS',margin='0.2',taxes='0.3'),
                               {('component',1):base('100','UN')}, Decimal('0.7442'))
        self.assertEqual(result.gross_price, Decimal('200.00'))
        self.assertEqual(result.net_price, Decimal('148.84'))
        with self.assertRaises(PricingError):
            calculate_sheet(sheet([row],basis='GROSS'),{('component',1):base('100','UN')})

    def test_external_service_and_tool_unit_cost_affect_price(self):
        row=dict(kind='service',base_id=1,quantity='2',consumption='0.5',unit='M2')
        result=calculate_sheet(sheet([row],tool_cost='3'),{('service',1):base('28','M2')})
        self.assertEqual(result.cost,Decimal('31'))

    def test_oldest_review_is_retained_and_snapshot_serializes(self):
        row=dict(kind='component',base_id=1,quantity='1',consumption='1',unit='UN')
        b=base('10','UN');b['reviewed_on']='2026-01-01'
        result=calculate_sheet(sheet([row]),{('component',1):b})
        self.assertEqual(result.reviewed_on,'2026-01-01')
        self.assertEqual(result.snapshot()['net_price'],'10.00')

    def test_invalid_inputs_and_unconfirmed_basis_never_publish(self):
        row=dict(kind='component',base_id=1,quantity='1',consumption='1',unit='UN')
        for overrides in [dict(efficiency='0'),dict(efficiency='1.01'),dict(margin='0.8',taxes='0.2'),
                          dict(confirmed=False),dict(basis='UNKNOWN'),dict(tool_cost='NaN')]:
            with self.subTest(overrides=overrides),self.assertRaises(PricingError):
                calculate_sheet(sheet([row],**overrides),{('component',1):base('100','UN')})
        for price in ('NaN','-2','Infinity'):
            with self.subTest(price=price),self.assertRaises(PricingError):
                calculate_sheet(sheet([row]),{('component',1):base(price,'UN')})

    def test_oversized_piece_unknown_units_and_inactive_inputs_fail(self):
        row=dict(kind='material',base_id=1,mode='BLANK',quantity='1',blank_length='300',
                 blank_width='200',piece_length='1000',piece_width='254')
        with self.assertRaises(PricingError):
            calculate_sheet(sheet([row]),{('material',1):base('10','KG',kg_m2='7.6')})
        row=dict(kind='component',base_id=1,quantity='1',consumption='1',unit='M')
        with self.assertRaises(PricingError):
            calculate_sheet(sheet([row]),{('component',1):base('10','KG')})


if __name__=='__main__': unittest.main()
