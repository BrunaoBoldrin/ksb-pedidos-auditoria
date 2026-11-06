import os
import unittest
from datetime import date
from unittest.mock import patch

import parser
from test_parser_price_review import ORDER_TEXT, FakePdf


class DynamicParserTests(unittest.TestCase):
    def process(self,reference):
        material=dict(codigo_material='WGS-5520',descricao='TESTE',material='LATÃO',norma='BRN 66',
                      ncm='7419.80.90',unidade_medida='PEÇ',preco_unitario_liquido=999,
                      data_ultima_revisao='2026-11-01')
        with patch.dict(os.environ,{'KSB_DYNAMIC_PRICING':'1'}), \
             patch.object(parser.pdfplumber,'open',return_value=FakePdf(ORDER_TEXT)), \
             patch.object(parser,'buscar_material_por_codigo',return_value=material), \
             patch.object(parser,'localizar_regra_fiscal_por_ncm',return_value=None), \
             patch('pricing_repository.PricingRepository.references',return_value=dict(version=8,items={'WGS-5520':reference})):
            return parser.processar_pdf('pedido.pdf',price_reference_date=date(2026,11,6))[1].iloc[0]

    def test_uses_published_sheet_instead_of_legacy_price(self):
        reference=dict(state='ACTIVE',price='100.00',revision=2,reviewed_on='2026-11-01',
                       unit='UN',snapshot_id=15,fiscal_context=dict(basis='NET'))
        row=self.process(reference)
        self.assertEqual(row['Status Comercial'],'OK')
        self.assertEqual(row['Preço Cadastrado'],100)
        self.assertEqual(row['Memória Preço ID'],15)
        self.assertEqual(row['Versão Precificação'],8)
        self.assertEqual(row['Contexto Precificação']['revision'],2)

    def test_missing_sheet_is_pending_even_with_legacy_price(self):
        row=self.process(dict(state='MISSING',price=None))
        self.assertIn('FOLHA',row['Status Comercial'])
        self.assertIn('FOLHA',row['Diagnóstico Comercial'])
        self.assertNotEqual(row['Preço Cadastrado'],999)


if __name__=='__main__':unittest.main()
