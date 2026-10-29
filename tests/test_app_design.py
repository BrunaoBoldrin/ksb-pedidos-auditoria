"""Real Streamlit screens with external database I/O isolated from tests."""

import hashlib
import re
import tempfile
import unittest
from contextlib import ExitStack, chdir
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

import database
import parser
import ui_components
from system_settings import SystemSettings


APP = Path(__file__).resolve().parents[1] / "app.py"


class AppDesignTests(unittest.TestCase):
    def setUp(self):
        self.external = ExitStack()
        self.addCleanup(self.external.close)
        for name in ("listar_materiais_completo", "listar_regras_fiscais", "listar_usuarios",
                     "listar_logs_auditorias", "listar_logs_revisoes_preco"):
            self.external.enter_context(patch.object(database, name, return_value=[]))
        self.settings_loader = self.external.enter_context(
            patch.object(database, "buscar_configuracoes_sistema", return_value=SystemSettings())
        )
        self.external.enter_context(
            patch.object(database, "listar_metadados_configuracoes", return_value={})
        )
        self.saved_settings = []
        self.external.enter_context(
            patch.object(
                database,
                "salvar_configuracoes_sistema",
                side_effect=lambda settings, user: self.saved_settings.append((settings, user)),
            )
        )
        self.writes = self.external.enter_context(patch.object(
            database, "registrar_auditoria_pedido",
            side_effect=AssertionError("A presentation rerun must not write an audit"),
        ))

    def app(self, profile="ADMIN"):
        at = AppTest.from_file(str(APP), default_timeout=15)
        at.session_state["usuario_logado"] = "demo"
        at.session_state["nome_usuario"] = "Usuário de teste"
        at.session_state["perfil_usuario"] = profile
        at.run()
        self.assertEqual(len(at.exception), 0)
        return at

    def cached_app(self):
        at = self.app()
        content = b"presentation fixture - no processing"
        at.file_uploader[0].set_value(("pedido.pdf", content, "application/pdf")).run()
        rows = pd.DataFrame([
            {"Pedido": "4501", "Item": "00010", "Código Material": "02154693", "Descrição": "Aprovado", "Status": "OK", "Status Comercial": "OK", "Preço Cadastrado": 100},
            {"Pedido": "4501", "Item": "00020", "Código Material": "WGS-5520", "Descrição": "Revisão", "Status": "OK", "Status Comercial": "PENDENTE - REVISÃO DE PREÇO", "Preço Cadastrado": 100, "Diagnóstico Comercial": "PREÇO NECESSITA DE REVISÃO: ATUALIZE O VALOR DO ITEM."},
        ])
        at.session_state["resultados_processados"] = [(rows.copy(), rows.copy())]
        at.session_state["assinatura_resultados"] = [("pedido.pdf", hashlib.sha256(content).hexdigest())]
        at.run()
        self.assertEqual(len(at.exception), 0)
        return at

    def test_cached_batch_survives_filter_rerun_without_new_audit(self):
        at = self.cached_app()
        at.radio(key="filtro_resultados").set_value("Com pendência").run()
        self.assertEqual(len(at.exception), 0)
        html = "\n".join(m.value for m in at.markdown)
        self.assertIn("WGS-5520", html)
        self.assertNotIn("02154693", html)
        self.assertIn("PREÇO NECESSITA DE REVISÃO: ATUALIZE O VALOR DO ITEM.", html)
        self.assertEqual(self.writes.call_count, 0)
        self.assertEqual(len(at.get("download_button")), 4)

    def test_changed_upload_invalidates_old_batch(self):
        at = self.cached_app()
        at.file_uploader[0].set_value(("outro.pdf", b"different", "application/pdf")).run()
        self.assertEqual(len(at.exception), 0)
        self.assertIsNone(at.session_state["resultados_processados"])
        html = "\n".join(m.value for m in at.markdown)
        self.assertNotIn("WGS-5520", html)
        self.assertEqual(self.writes.call_count, 0)

    def test_navigation_round_trip_preserves_batch_but_explicit_removal_clears_it(self):
        at = self.cached_app()
        at.sidebar.button(key="nav_📦 Itens Cadastrados").click().run()
        at.sidebar.button(key="nav_📄 Análise de Pedidos KSB").click().run()
        self.assertEqual(len(at.exception), 0)
        self.assertIsNotNone(at.session_state["resultados_processados"])
        self.assertEqual(len(at.get("download_button")), 4)
        self.assertEqual(self.writes.call_count, 0)

        at = self.cached_app()
        at.file_uploader[0].set_value([]).run()
        self.assertEqual(len(at.exception), 0)
        self.assertIsNone(at.session_state["resultados_processados"])
        self.assertEqual(len(at.get("download_button")), 0)
        self.assertEqual(self.writes.call_count, 0)

    def test_process_action_persists_once_and_download_rerun_keeps_batch(self):
        at = self.cached_app()
        results = at.session_state["resultados_processados"][0]
        self.writes.side_effect = None
        with tempfile.TemporaryDirectory() as directory, chdir(directory), patch.object(
            parser, "processar_pdf", return_value=results
        ) as processor, patch.object(parser, "extract_order_number", return_value="4501"), patch.object(
            database, "pedido_ja_aprovado", return_value=False
        ):
            next(b for b in at.button if b.label == "Processar pedidos").click().run()
            self.assertEqual(len(at.exception), 0)
            self.assertEqual(self.writes.call_count, 1)
            self.assertEqual(self.writes.call_args.kwargs["usuario"], "Usuário de teste")
            self.assertEqual(processor.call_args.kwargs["settings"], SystemSettings())
            self.assertIsNotNone(at.session_state["resultados_processados"])
            # A download's default rerun uses the same presentation path.
            at.run()
            self.assertEqual(len(at.exception), 0)
            self.assertEqual(self.writes.call_count, 1)
            self.assertEqual(len(at.get("download_button")), 4)

    def test_login_and_registration_forms_render_with_native_controls(self):
        at = AppTest.from_file(str(APP), default_timeout=15).run()
        self.assertEqual(len(at.exception), 0)
        with patch.object(database, "buscar_usuario_login", return_value=(1, "Teste", "demo", "ADMIN")):
            at.text_input[0].set_value("demo")
            at.text_input[1].set_value("fixture-password")
            next(b for b in at.button if b.label == "Entrar").click().run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(at.session_state["usuario_logado"], "demo")
        for menu, action, label in [
            ("📦 Itens Cadastrados", "➕ Novo Material", "Código Material KSB"),
            ("🏛 Regras Fiscais", "➕ Nova Regra", "NCM"),
            ("👤 Usuários", "➕ Novo Usuário", "Nome"),
        ]:
            with self.subTest(menu=menu):
                at.sidebar.button(key=f"nav_{menu}").click().run()
                next(b for b in at.button if b.label == action).click().run()
                self.assertEqual(len(at.exception), 0)
                self.assertIn(label, [w.label for w in at.text_input])
        self.assertEqual(self.writes.call_count, 0)

    def test_logout_clears_cached_results(self):
        at = self.cached_app()
        at.button(key="sair_conta").click().run()
        self.assertEqual(len(at.exception), 0)
        self.assertIsNone(at.session_state["usuario_logado"])
        self.assertNotIn("resultados_processados", at.session_state)
        self.assertEqual([w.label for w in at.text_input], ["Usuário", "Senha"])

    def test_every_authorized_menu_renders_without_database_writes(self):
        headings = {
            "📄 Análise de Pedidos KSB": "Análise de Pedidos",
            "📦 Itens Cadastrados": "Itens Cadastrados",
            "💰 Revisão de Preços": "Revisão de Preços",
            "🏛 Regras Fiscais": "Regras Fiscais",
            "🧾 Log": "Log",
            "👤 Usuários": "Usuários",
            "⚙️ Configurações": "Configurações",
            "🛠️ Ferramentas Administrativas": "Ferramentas Administrativas",
        }
        expected = {
            "ADMIN": ["📄 Análise de Pedidos KSB", "📦 Itens Cadastrados", "💰 Revisão de Preços", "🏛 Regras Fiscais", "🧾 Log", "👤 Usuários", "⚙️ Configurações", "🛠️ Ferramentas Administrativas"],
            "VENDEDORA": ["📄 Análise de Pedidos KSB", "📦 Itens Cadastrados"],
            "PROCESSISTA": ["📦 Itens Cadastrados"],
            "OUTRO": ["📄 Análise de Pedidos KSB"],
        }
        for profile, menus in expected.items():
            with self.subTest(profile=profile):
                at = self.app(profile)
                self.assertEqual([b.label for b in at.sidebar.button if (b.key or "").startswith("nav_")], menus)
                self.assertEqual(len(at.sidebar.radio), 0)
                for menu in menus:
                    at.sidebar.button(key=f"nav_{menu}").click().run()
                    self.assertEqual(len(at.exception), 0, menu)
                    self.assertEqual(at.session_state["pagina_atual"], menu)
                    self.assertIn(f"<h1>{headings[menu]}</h1>", "\n".join(m.value for m in at.markdown))
                at.run()
                self.assertEqual(at.session_state["pagina_atual"], menus[-1])
        self.assertEqual(self.writes.call_count, 0)

    def test_admin_can_edit_and_save_system_settings(self):
        at = self.app()
        at.sidebar.button(key="nav_⚙️ Configurações").click().run()

        inputs = {widget.label: widget for widget in at.number_input}
        self.assertEqual(inputs["Validade da revisão de preço (dias)"].value, 90)
        self.assertEqual(inputs["Tolerância de diferença de preço (R$)"].value, 0.01)
        self.assertEqual(inputs["Tolerância de diferença fiscal (R$)"].value, 1.0)

        inputs["Validade da revisão de preço (dias)"].set_value(120)
        inputs["Tolerância de diferença de preço (R$)"].set_value(0.5)
        inputs["Tolerância de diferença fiscal (R$)"].set_value(2.0)
        next(button for button in at.button if button.label == "💾 Salvar configurações").click().run()

        self.assertEqual(
            self.saved_settings,
            [(SystemSettings(120, 0.5, 2.0), "Usuário de teste")],
        )

    def test_native_tables_do_not_create_a_second_scroll_container(self):
        at = self.app()
        injected_styles = "\n".join(
            markdown.value
            for markdown in at.markdown
            if "stDataFrame" in markdown.value or "stDataEditor" in markdown.value
        )

        table_rule = re.search(
            r'\[data-testid="stDataFrame"\].*?\{(?P<declarations>[^}]*)\}',
            injected_styles,
            flags=re.DOTALL,
        )

        self.assertIsNotNone(table_rule)
        self.assertRegex(table_rule.group("declarations"), r"overflow\s*:\s*hidden\s*;")

    def test_table_pages_offer_excel_downloads(self):
        material = (
            "001492536", "PROTETOR ACOPL", "LATÃO", "BRN66/C08", "7419.80.90",
            "PEÇAS", "DI039501430000", "DI039503930000", 405.62,
            "2026-01-01", "Administrador",
        )
        with patch.object(database, "listar_materiais_completo", return_value=[material]), patch.object(
            database,
            "listar_logs_auditorias",
            return_value=[("4501", "PRIMEIRA ANÁLISE", "OK", "OK", "Ana", "2026-10-23T17:44:51+00:00", False, False, "pedido.pdf")],
        ), patch.object(
            database,
            "listar_logs_revisoes_preco",
            return_value=[("001492536", "PROTETOR ACOPL", 400.0, 405.62, "Ana", "2026-10-23T17:44:51+00:00", "ALTERAÇÃO PELO SISTEMA")],
        ), patch.object(
            database,
            "listar_regras_fiscais",
            return_value=[(1, "7419.80.90", 12.0, 3.25, "LATÃO", 1)],
        ), patch.object(
            database,
            "listar_usuarios",
            return_value=[(1, "Administrador", "admin", "ADMIN", 1)],
        ):
            at = self.app()
            expected_by_menu = {
                "📦 Itens Cadastrados": ["📥 Baixar banco completo de itens em Excel"],
                "💰 Revisão de Preços": ["📥 Baixar preços desatualizados em Excel"],
                "🧾 Log": ["📥 Baixar auditorias em Excel", "📥 Baixar revisões de preços em Excel"],
                "🏛 Regras Fiscais": ["📥 Baixar regras fiscais em Excel"],
                "👤 Usuários": ["📥 Baixar usuários em Excel"],
            }

            for menu, expected_labels in expected_by_menu.items():
                with self.subTest(menu=menu):
                    at.sidebar.button(key=f"nav_{menu}").click().run()
                    labels = [button.label for button in at.get("download_button")]
                    for label in expected_labels:
                        self.assertIn(label, labels)

    def test_items_download_uses_the_complete_database_not_the_300_row_preview(self):
        materials = [
            (
                f"{index:09d}", f"Material {index}", "AÇO", "NORMA", "0000.00.00",
                "PEÇAS", f"J{index:09d}", f"V{index:09d}", float(index),
                "2026-01-01", "Administrador",
            )
            for index in range(301)
        ]
        real_exporter = ui_components.dataframe_to_excel_bytes

        with patch.object(database, "listar_materiais_completo", return_value=materials), patch.object(
            ui_components,
            "dataframe_to_excel_bytes",
            wraps=real_exporter,
        ) as exporter:
            at = self.app()
            at.sidebar.button(key="nav_📦 Itens Cadastrados").click().run()

            self.assertEqual(len(at.exception), 0)
            self.assertEqual(len(at.dataframe[0].value), 300)
            exported_items = next(
                call.args[0]
                for call in exporter.call_args_list
                if call.args[1] == "Itens"
            )
            self.assertEqual(len(exported_items), 301)

    def test_price_tables_display_brazilian_currency(self):
        material = (
            "001492536", "PROTETOR ACOPL", "LATÃO", "BRN66/C08", "7419.80.90",
            "PEÇAS", "DI039501430000", "DI039503930000", 1234.5,
            "2026-01-01", "Administrador",
        )
        price_log = (
            "001492536", "PROTETOR ACOPL", 1000.0, 1234.5, "Ana",
            "2026-10-23T17:44:51+00:00", "ALTERAÇÃO PELO SISTEMA",
        )
        with patch.object(database, "listar_materiais_completo", return_value=[material]), patch.object(
            database, "listar_logs_revisoes_preco", return_value=[price_log]
        ):
            at = self.app()

            at.sidebar.button(key="nav_📦 Itens Cadastrados").click().run()
            self.assertEqual(at.dataframe[0].value.loc[0, "Preço Unitário Líquido"], "R$ 1.234,50")

            at.sidebar.button(key="nav_💰 Revisão de Preços").click().run()
            self.assertEqual(at.dataframe[0].value.loc[0, "Preço Unitário Líquido"], "R$ 1.234,50")

            at.sidebar.button(key="nav_🧾 Log").click().run()
            self.assertEqual(at.dataframe[1].value.loc[0, "Preço Anterior"], "R$ 1.000,00")
            self.assertEqual(at.dataframe[1].value.loc[0, "Preço Novo"], "R$ 1.234,50")

    def test_reaudit_stays_disabled_until_both_literal_confirmations(self):
        at = self.app()
        content = b"approved order fixture"
        at.file_uploader[0].set_value(("aprovado.pdf", content, "application/pdf")).run()
        at.session_state["pedidos_reavaliacao_pendentes"] = ["4501"]
        at.session_state["arquivos_reavaliacao_pendentes"] = [("aprovado.pdf", hashlib.sha256(content).hexdigest())]
        at.run()
        self.assertEqual(at.checkbox[0].label, "Estou ciente de que este pedido já foi auditado e desejo reavaliá-lo.")
        self.assertEqual(at.checkbox[1].label, "Confirmei se este pedido já foi emitido/implantado.")
        action = next(b for b in at.button if "REAVALIAR" in b.label.upper())
        self.assertTrue(action.disabled)
        at.checkbox[0].check().run()
        self.assertTrue(next(b for b in at.button if "REAVALIAR" in b.label.upper()).disabled)
        at.checkbox[1].check().run()
        self.assertFalse(next(b for b in at.button if "REAVALIAR" in b.label.upper()).disabled)
        self.assertEqual(self.writes.call_count, 0)


if __name__ == "__main__":
    unittest.main()
