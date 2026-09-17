import sys
import types
import unittest
from unittest.mock import patch


database = types.ModuleType("database")
database.buscar_material_por_codigo = lambda codigo: None
database.localizar_regra_fiscal_por_ncm = lambda ncm: None
sys.modules["database"] = database

import parser


class PaginaFalsa:
    def __init__(self, texto):
        self.texto = texto

    def extract_text(self):
        return self.texto


class PdfFalso:
    def __init__(self, texto):
        self.pages = [PaginaFalsa(texto)]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def bloco_item(item, codigo, descricao, total):
    return f"""
{item} {codigo} 25.09.2026 1 PEÇ 406,69/1 {total}
       {descricao}
tamanho/dimensão: 154/72/22/214/190
Mat.básic: LATÃO
Desenho/Norma: BRN 66/C08 01
NCM: 7419.80.90
"""


class TestIdentificacaoItens(unittest.TestCase):
    def test_codigos_alfanumericos_entram_na_extracao_e_diagnostico(self):
        codigos = ["02154693", "WGS-5520", "AB1234", "wgs-5520"]
        itens = ["00010", "00100", "00110", "00120"]
        texto = "Pedido 4508000000\nData 30.06.2026\n" + "".join(
            bloco_item(item, codigo, f"DESCRICAO {codigo}", f"{i * 100},00")
            for i, (item, codigo) in enumerate(zip(itens, codigos), 1)
        )
        with patch.object(parser.pdfplumber, "open", return_value=PdfFalso(texto)), patch.object(
            parser, "buscar_material_por_codigo", return_value=None
        ) as buscar:
            dados, analises = parser.processar_pdf("pedido.pdf")

        self.assertEqual(dados["Item"].tolist(), itens)
        self.assertEqual(dados["Codigo Material"].tolist(), codigos)
        self.assertEqual(analises["Código Material"].tolist(), codigos)
        self.assertEqual(dados["Descricao"].tolist(), [f"DESCRICAO {c}" for c in codigos])
        self.assertEqual(dados["Valor Total"].tolist(), ["100,00", "200,00", "300,00", "400,00"])
        self.assertEqual(dados["Quantidade"].tolist(), ["1"] * 4)
        self.assertEqual(dados["Data Entrega"].tolist(), ["25.09.2026"] * 4)
        self.assertEqual([chamada.args[0] for chamada in buscar.call_args_list], codigos)

    def test_cabecalho_nao_usa_a_proxima_linha_como_codigo(self):
        self.assertIsNone(parser.PADRAO_CABECALHO_ITEM.search("00010\nWGS-5520"))
        self.assertIsNone(parser.PADRAO_CABECALHO_ITEM.search("00010 WGS-5520!"))

    def processar_texto(self, texto):
        with patch.object(parser.pdfplumber, "open", return_value=PdfFalso(texto)):
            dados, _ = parser.processar_pdf("pedido.pdf")
        return dados

    def test_reconhece_itens_com_centena_no_sequencial(self):
        texto = """
Pedido 4508110523
Data 30.06.2026
""" + "".join(
            [
                bloco_item("00010", "02152148", "ITEM 1", "4.590,33"),
                bloco_item("00100", "01492530", "ITEM 10", "525,79"),
                bloco_item("00110", "01492530", "ITEM 11", "525,79"),
                bloco_item("00120", "05118836", "ITEM 12", "2.981,91"),
            ]
        )

        dados = self.processar_texto(texto)

        self.assertEqual(dados["Item"].tolist(), ["00010", "00100", "00110", "00120"])
        self.assertEqual(
            dados["Codigo Material"].tolist(),
            ["02152148", "01492530", "01492530", "05118836"],
        )
        self.assertEqual(dados["Descricao"].tolist(), ["ITEM 1", "ITEM 10", "ITEM 11", "ITEM 12"])
        self.assertEqual(dados["Valor Total"].tolist(), ["4.590,33", "525,79", "525,79", "2.981,91"])

    def test_mantem_compatibilidade_com_sequencial_antigo(self):
        texto = """
Pedido 4508000000
Data 30.06.2026
""" + "".join(
            [
                bloco_item("00010", "02152148", "ITEM 1", "100,00"),
                bloco_item("00020", "01492530", "ITEM 2", "200,00"),
                bloco_item("00030", "05118836", "ITEM 3", "300,00"),
            ]
        )

        dados = self.processar_texto(texto)

        self.assertEqual(dados["Item"].tolist(), ["00010", "00020", "00030"])


if __name__ == "__main__":
    unittest.main()
