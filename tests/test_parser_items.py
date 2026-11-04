import unittest
from unittest.mock import patch

import parser
import ui_components


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
    def setUp(self):
        for name in ("buscar_material_por_codigo", "localizar_regra_fiscal_por_ncm"):
            mocked = patch.object(parser, name, return_value=None)
            mocked.start()
            self.addCleanup(mocked.stop)

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

    def test_analise_inclui_codigos_internos_e_data_de_entrega(self):
        texto = """
Pedido 4508000000
Data 30.06.2026
Endereço de entrega: KSB Brasil Ltda. Jundiaí - SP
""" + bloco_item("00010", "WGS-5520", "ITEM OPERACIONAL", "406,69")
        material = {
            "codigo_material": "WGS-5520",
            "descricao": "ITEM OPERACIONAL",
            "material": "LATÃO",
            "norma": "BRN 66/C08 01",
            "ncm": "7419.80.90",
            "unidade_medida": "PEÇ",
            "codigo_interno_jundiai": "GL-JDI-5520",
            "codigo_interno_varzea": "GL-VAR-5520",
            "preco_unitario_liquido": 406.69,
            "data_ultima_revisao": "01/11/2026",
            "usuario_ultima_revisao_preco": "Admin",
        }

        with patch.object(parser.pdfplumber, "open", return_value=PdfFalso(texto)), patch.object(
            parser, "buscar_material_por_codigo", return_value=material
        ):
            _, analises = parser.processar_pdf("pedido.pdf")

        self.assertEqual(analises.loc[0, "Código Interno Jundiaí"], "GL-JDI-5520")
        self.assertEqual(analises.loc[0, "Código Interno Várzea"], "GL-VAR-5520")
        self.assertEqual(analises.loc[0, "Data Entrega"], "25.09.2026")

    def test_analise_de_material_nao_cadastrado_mantem_codigos_internos_vazios(self):
        texto = "Pedido 4508000000\nData 30.06.2026\n" + bloco_item(
            "00010", "SEM-CADASTRO", "ITEM SEM CADASTRO", "100,00"
        )

        with patch.object(parser.pdfplumber, "open", return_value=PdfFalso(texto)):
            _, analises = parser.processar_pdf("pedido.pdf")

        self.assertEqual(analises.loc[0, "Código Interno Jundiaí"], "")
        self.assertEqual(analises.loc[0, "Código Interno Várzea"], "")

    def test_endereco_completo_define_unidade_e_codigo_gloria_corretos(self):
        material = {
            "codigo_material": "WGS-5520",
            "descricao": "ITEM OPERACIONAL",
            "material": "LATÃO",
            "norma": "BRN 66/C08 01",
            "ncm": "7419.80.90",
            "unidade_medida": "PEÇ",
            "codigo_interno_jundiai": "GL-JDI-5520",
            "codigo_interno_varzea": "GL-VAR-5520",
            "preco_unitario_liquido": 406.69,
            "data_ultima_revisao": "01/11/2026",
            "usuario_ultima_revisao_preco": "Admin",
        }
        casos = [
            (
                """Endereço de entrega:
KSB Brasil Ltda.
Av. Comendador Antônio Borin, 3500 - Distrito Industrial
Jundiaí - SP
""",
                "Jundiaí",
                "GL-JDI-5520",
            ),
            (
                """Endereço de entrega:
KSB Brasil Ltda.
Rua José Rabelo Portella, 400 - Jardim Maria de Fátima
Várzea Paulista - SP
""",
                "Várzea",
                "GL-VAR-5520",
            ),
            (
                """Endereço de entrega:
KSB Brasil Ltda.
Rua Jundiaí, 100 - Jardim Paulista
Várzea Paulista - SP
""",
                "Várzea",
                "GL-VAR-5520",
            ),
            (
                """Endereço de entrega:
KSB Brasil Ltda.
Rua Exemplo, 100
13213 180 Jundiaí - SP
""",
                "Jundiaí",
                "GL-JDI-5520",
            ),
        ]

        for endereco, unidade_esperada, codigo_esperado in casos:
            with self.subTest(unidade=unidade_esperada):
                texto = (
                    "Pedido 4508000000\nData 30.06.2026\n"
                    + endereco
                    + bloco_item("00010", "WGS-5520", "ITEM OPERACIONAL", "406,69")
                )
                with patch.object(parser.pdfplumber, "open", return_value=PdfFalso(texto)), patch.object(
                    parser, "buscar_material_por_codigo", return_value=material
                ):
                    _, analises = parser.processar_pdf("pedido.pdf")

                linha = analises.iloc[0]
                self.assertEqual(linha["Unidade Pedido"], unidade_esperada)
                self.assertEqual(ui_components.selecionar_codigo_gloria(linha), codigo_esperado)


if __name__ == "__main__":
    unittest.main()
