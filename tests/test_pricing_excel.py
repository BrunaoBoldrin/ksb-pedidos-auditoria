"""Synthetic source sheets: outputs are computed, never copied from cached totals."""
import unittest
from io import BytesIO
from zipfile import ZipFile,ZIP_DEFLATED
from openpyxl import Workbook
from pricing_excel import import_workbook,recalculate


def workbook(cells):
    book=Workbook();sheet=book.active;sheet.title='Orç Conj Final'
    for address,value in cells.items():sheet[address]=value
    stream=BytesIO();book.save(stream)
    return stream.getvalue()


class ExcelPricingTests(unittest.TestCase):
    def source(self,**extra):
        return import_workbook(workbook(dict({'B10':'custo total','H10':'=SUM(D1:D2)','M10':'=ROUNDUP(H10/(1-K9-N9),0)',
            'V5':'=M10/T5','T5':2,'K9':.2,'N9':.3,'D1':10,'D2':2},**extra)))

    def test_recalculates_cost_and_rounds_source_lot_before_unit_price(self):
        model=self.source();result=recalculate(model,{'D1':'10,25'})
        self.assertEqual(result['cost_total'],'12.25');self.assertEqual(result['cost_per_piece'],'6.125')
        self.assertEqual(result['gross_total'],'25');self.assertEqual(result['gross_per_piece'],'12.5')
        self.assertEqual(model['cells']['D1']['value'],'10')

    def test_if_is_lazy_and_accepts_decimal_text_returned_by_source(self):
        model=self.source(D1='=IF(V1=1,"92,08",IF(V1=2,"138,12",1/0))*1',V1=1)
        self.assertEqual(recalculate(model)['cost_total'],'94.08')
        self.assertEqual(recalculate(model,{'V1':2})['cost_total'],'140.12')
        result=recalculate(model,{'V1':3})
        self.assertIsNone(result['cost_total']);self.assertIn('D1',result['errors'])

    def test_invalid_edits_do_not_modify_formulas_or_accept_nonfinite_values(self):
        model=self.source()
        for edits in ({'H10':'0'},{'ZZ99':1},{'D1':'NaN'},{'D1':'Infinity'},{'D1':'texto'}):
            with self.subTest(edits=edits),self.assertRaises(ValueError):recalculate(model,edits)

    def test_auxiliary_cycle_and_unsupported_formula_do_not_hide_valid_outputs(self):
        result=recalculate(self.source(Z1='=Z2',Z2='=Z1',Y1='=WEBSERVICE("https://example.com")'))
        self.assertEqual(result['gross_total'],'24');self.assertIn('Z1',result['errors']);self.assertIn('Y1',result['errors'])

    def test_blank_reference_matches_excel_and_suspicious_reference_is_reported(self):
        result=recalculate(self.source(Z1='=M10/(1-H571)'))
        self.assertEqual(result['values']['Z1'],'24')
        self.assertTrue(any('H571' in warning for warning in result['warnings']))

    def test_external_lookup_is_explicit_input_but_internal_cache_is_not_used(self):
        data=workbook({'B10':'custo total','H10':'=D1*2','M10':'=ROUNDUP(H10,0)','T5':1,
                       'D1':"=VLOOKUP(A1,'[1]Custos'!A1:B10,2,FALSE)",'A1':'Aço'})
        source=BytesIO()
        with ZipFile(BytesIO(data)) as incoming,ZipFile(source,'w',ZIP_DEFLATED) as outgoing:
            for item in incoming.infolist():
                content=incoming.read(item.filename)
                if item.filename=='xl/worksheets/sheet1.xml':
                    content=content.replace(b'</f><v></v>',b'</f><v>999</v>')
                outgoing.writestr(item,content)
        model=import_workbook(source.getvalue())
        self.assertTrue(model['cells']['D1']['external']);self.assertTrue(model['cells']['D1']['editable'])
        result=recalculate(model,{'D1':'3,25'})
        self.assertEqual(result['cost_total'],'6.5');self.assertEqual(result['gross_total'],'7')

    def test_numeric_ranges_percent_and_roundup_negative_are_supported(self):
        result=recalculate(self.source(D1='=ROUNDUP(-1.234,2)+2^3+10%'))
        self.assertEqual(result['values']['D1'],'6.86')

    def test_excessive_ranges_are_rejected_without_workbook_evaluation_hang(self):
        result=recalculate(self.source(Z1='=SUM(A1:XFD1048576)'))
        self.assertIn('Z1',result['errors']);self.assertEqual(result['gross_total'],'24')

    def test_external_lookup_without_cached_value_requires_an_explicit_input(self):
        model=self.source(D1="=VLOOKUP(A1,'[1]Custos'!A1:B10,2,FALSE)",A1='Aço')
        result=recalculate(model)
        self.assertIn('D1',result['errors'])
        self.assertIsNone(result['cost_total']);self.assertIsNone(result['gross_total'])
        for empty in (None,''):
            result=recalculate(model,{'D1':empty})
            self.assertIsNone(result['cost_total'])
        self.assertEqual(recalculate(model,{'D1':'0'})['cost_total'],'2')

    def test_extreme_numeric_exponents_are_rejected_before_expansion(self):
        model=self.source()
        for value in ('1e-1000000','1e1000000','0.'+'0'*300+'1'):
            with self.subTest(value=value[:30]),self.assertRaises(ValueError):
                recalculate(model,{'T5':value})

    def test_per_piece_overflow_is_a_managed_calculation_error(self):
        model=self.source(D1='=1e24',D2=0,K9=0,N9=0)
        result=recalculate(model,{'T5':'1e-24'})
        self.assertIsNone(result['cost_per_piece'])
        self.assertTrue(result['errors'])
