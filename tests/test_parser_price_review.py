import sys
import types
import unittest
from datetime import date
from unittest.mock import patch


database = types.ModuleType("database")
database.buscar_material_por_codigo = lambda codigo: None
database.localizar_regra_fiscal_por_ncm = lambda ncm: None
sys.modules["database"] = database

import parser


class FakePage:
    def __init__(self, text):
        self.text = text

    def extract_text(self):
        return self.text


class FakePdf:
    def __init__(self, text):
        self.pages = [FakePage(text)]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


ORDER_TEXT = """
Pedido 4508999999
Data 30.06.2026
00010 WGS-5520 25.12.2026 1 PEÇ 100,00/1 100,00
       PEÇA TESTE
tamanho/dimensão: 154/72/22/214/190
Mat.básic: LATÃO
Desenho/Norma: BRN 66/C08 01
NCM: 7419.80.90
"""


class ParserPriceReviewTests(unittest.TestCase):
    def registered_material(self, review_date):
        return {
            "codigo_material": "WGS-5520",
            "descricao": "PEÇA TESTE",
            "material": "LATÃO",
            "norma": "BRN 66/C08",
            "ncm": "7419.80.90",
            "unidade_medida": "PEÇ",
            "preco_unitario_liquido": 100.0,
            "data_ultima_revisao": review_date,
            "usuario_ultima_revisao_preco": "Administrador",
        }

    def process(self, review_date, reference_date):
        with patch.object(parser.pdfplumber, "open", return_value=FakePdf(ORDER_TEXT)), patch.object(
            parser,
            "buscar_material_por_codigo",
            return_value=self.registered_material(review_date),
        ):
            _, analysis = parser.processar_pdf(
                "pedido.pdf",
                price_reference_date=reference_date,
            )
        return analysis.iloc[0]

    def test_equal_but_outdated_price_is_pending_with_mandatory_message(self):
        item = self.process("2026-06-30", date(2026, 10, 1))

        self.assertEqual(item["Status Comercial"], "PENDENTE - REVISÃO DE PREÇO")
        self.assertIn(
            "PREÇO NECESSITA DE REVISÃO: ATUALIZE O VALOR DO ITEM.",
            item["Diagnóstico Comercial"],
        )
        self.assertNotEqual(item["Status Comercial"], "OK")

    def test_extracts_order_number_without_running_full_analysis(self):
        with patch.object(parser.pdfplumber, "open", return_value=FakePdf(ORDER_TEXT)):
            self.assertEqual(parser.extract_order_number("pedido.pdf"), "4508999999")

    def test_full_processing_reuses_shared_pdf_text_reader(self):
        with patch.object(parser, "extract_pdf_text", return_value=ORDER_TEXT) as reader, patch.object(
            parser,
            "buscar_material_por_codigo",
            return_value=self.registered_material("2026-10-01"),
        ):
            data, analysis = parser.processar_pdf(
                "pedido.pdf",
                price_reference_date=date(2026, 10, 22),
            )

        reader.assert_called_once_with("pedido.pdf")
        self.assertEqual(data["Item"].tolist(), ["00010"])
        self.assertEqual(analysis.iloc[0]["Status Comercial"], "OK")


if __name__ == "__main__":
    unittest.main()
