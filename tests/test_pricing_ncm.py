"""Current sheet calculations use the registered NCM, never a manual tax profile."""
import unittest
import json
from decimal import Decimal

from pricing_service import PricingService
from pricing_calculator import PricingError


class CalculationCursor:
    """Only the database boundary is replaced; arithmetic and service are real."""
    def __init__(self, ncm='7325.99.10', icms=18, ipi=6.5):
        self.rule=dict(ncm=ncm,unidade_medida='UN',aliquota_icms=icms,aliquota_ipi=ipi,rule_id=1)
        self.bases=[dict(id=i,code=str(i),description='Componente',unit='UN',price='100',factor='1',active=True,version=1,reviewed_on='2026-11-06') for i in range(1,101)]
        self.queries=[];self.result=[]

    def execute(self,sql,params=None):
        self.queries.append(sql)
        if 'pricing_profiles' in sql:
            self.result=[dict(data=dict(efficiency='1',taxes='.3',rounding='CENT'),active=True,reviewed_on='2026-11-06')]
        elif 'pricing_components' in sql:
            ids=params[0] if isinstance(params[0],list) else [params[0]]
            rows=[b for b in self.bases if b['id'] in ids]
            self.result=[dict(kind='component',base=json.dumps(b)) for b in rows] if 'to_jsonb' in sql else rows
        elif 'materiais' in sql:self.result=[self.rule]
        else:raise AssertionError(sql)

    def fetchone(self):return self.result[0] if self.result else None
    def fetchall(self):return self.result


class AutomaticNCMTests(unittest.TestCase):
    def revision(self,**changes):
        data=dict(lines=[dict(kind='component',base_id=1)],margin='.2',taxes='.3',commission='0',efficiency='1',rounding='CENT',reviewed_on='2026-11-06',basis='',confirmed=False)
        data.update(changes)
        return dict(material_code='001',profile_id=99,data=data)

    def test_unconfirmed_import_shows_final_and_net_from_registered_ncm(self):
        try:result,context=PricingService()._calculate(CalculationCursor(),self.revision())
        except PricingError as exc:self.fail(f'Rascunho válido deve ter prévia automática: {exc}')
        self.assertEqual(result.gross_price,Decimal('183.76'))
        self.assertEqual(result.net_price,Decimal('136.75'))
        self.assertEqual(result.parameters['taxes'],Decimal('.2558'))
        self.assertEqual(context['source'],'NCM')
        self.assertEqual(context['ipi'],'6.5')
        self.assertEqual(result.snapshot()['ipi_amount'],'11.94')
        self.assertEqual(result.snapshot()['total_with_ipi'],'195.70')

    def test_manual_tax_and_legacy_basis_cannot_override_item_rule(self):
        result,_=PricingService()._calculate(CalculationCursor(icms=12),self.revision(taxes='.01',basis='NET',confirmed=True))
        self.assertEqual(result.gross_price,Decimal('167.06'))
        self.assertEqual(result.net_price,Decimal('133.41'))

    def test_missing_invalid_ncm_or_missing_rate_never_assumes_tax(self):
        for ncm,icms in [('',18),('nan',18),('123',18),('73259910',None),('73259910',-1),('73259910',100)]:
            with self.subTest(ncm=ncm,icms=icms),self.assertRaises(PricingError):
                PricingService()._calculate(CalculationCursor(ncm=ncm,icms=icms),self.revision(basis='NET',confirmed=True))

    def test_large_sheet_reads_costs_in_batch(self):
        cursor=CalculationCursor()
        data=self.revision(basis='NET',confirmed=True,lines=[dict(kind='component',base_id=i) for i in range(1,101)])
        PricingService()._calculate(cursor,data)
        cost_queries=[q for q in cursor.queries if 'pricing_components' in q]
        self.assertLessEqual(len(cost_queries),1,'100 custos não devem exigir 100 consultas')


if __name__=='__main__':unittest.main()
