import unittest
from html.parser import HTMLParser

import pandas as pd

from ui_components import (
    cabecalho_item_html,
    filtrar_itens,
    painel_diagnostico_html,
    resumo_lote,
)


class MarkupReader(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)

    def handle_data(self, text):
        self.text.append(text)


class PresentationTests(unittest.TestCase):
    def setUp(self):
        self.frame = pd.DataFrame([
            {"Pedido": "4501", "Item": "00010", "Código Material": "02154693", "Status": "OK", "Status Comercial": "OK"},
            {"Pedido": "4501", "Item": "00020", "Código Material": "WGS-5520", "Status": "OK", "Status Comercial": "PENDENTE - REVISÃO DE PREÇO", "Preço Pedido KSB": 100, "Preço Cadastrado": 100},
            {"Pedido": "4502", "Item": "00100", "Código Material": "00123456", "Status": "DIVERGENTE", "Status Comercial": "OK"},
            {"Pedido": "4502", "Item": "00110", "Código Material": "ABC-1", "Status": None, "Status Comercial": pd.NA},
        ])

    def test_summary_does_not_approve_expired_equal_prices_or_incomplete_items(self):
        self.assertEqual(resumo_lote(self.frame), {
            "total": 4, "aprovados": 1, "pendentes": 3,
            "revisao_preco": 1, "divergencia_fiscal": 1,
        })

    def test_empty_or_missing_statuses_never_count_as_approved(self):
        self.assertEqual(resumo_lote(pd.DataFrame())["total"], 0)
        result = resumo_lote(pd.DataFrame([{"Item": "00010"}]))
        self.assertEqual((result["aprovados"], result["pendentes"]), (0, 1))

    def test_visual_filter_preserves_text_codes_and_does_not_mutate_source(self):
        original = self.frame.copy(deep=True)
        pending = filtrar_itens(self.frame, "Com pendência")
        self.assertEqual(pending["Item"].tolist(), ["00020", "00100", "00110"])
        self.assertEqual(pending.iloc[0]["Código Material"], "WGS-5520")
        selected = filtrar_itens(self.frame, "Aprovados", "4501")
        self.assertEqual(selected["Item"].tolist(), ["00010"])
        self.assertTrue(filtrar_itens(self.frame, "Todos", "inexistente").empty)
        pd.testing.assert_frame_equal(original, self.frame)

    def test_untrusted_item_content_is_rendered_as_text(self):
        markup = cabecalho_item_html({
            "Pedido": "4501", "Item": "00020", "Código Material": "WGS-5520",
            "Descrição": '<script>alert("x")</script><img src=x onerror=alert(1)>',
            "Status": "OK", "Status Comercial": '<svg onload="attack">',
        })
        reader = MarkupReader()
        reader.feed(markup)
        self.assertNotIn("script", reader.tags)
        self.assertNotIn("img", reader.tags)
        self.assertNotIn("svg", reader.tags)
        self.assertIn('<script>alert("x")</script>', "".join(reader.text))
        self.assertIn("00020", "".join(reader.text))
        self.assertIn("WGS-5520", "".join(reader.text))

    def test_pending_diagnostic_retains_complete_message_and_line_breaks(self):
        message = "PREÇO NECESSITA DE REVISÃO: ATUALIZE O VALOR DO ITEM.\nÚltima revisão: 22/07/2026"
        markup = painel_diagnostico_html("Comercial", "PENDENTE - REVISÃO DE PREÇO", message)
        reader = MarkupReader()
        reader.feed(markup)
        self.assertIn("br", reader.tags)
        self.assertIn("PREÇO NECESSITA DE REVISÃO: ATUALIZE O VALOR DO ITEM.", "".join(reader.text))
        self.assertIn("Última revisão: 22/07/2026", "".join(reader.text))


if __name__ == "__main__":
    unittest.main()
