"""Real Streamlit screens with external database I/O isolated from tests."""

import hashlib
import tempfile
import unittest
from contextlib import ExitStack, chdir
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

import database
import parser


APP = Path(__file__).resolve().parents[1] / "app.py"


class AppDesignTests(unittest.TestCase):
    def setUp(self):
        self.external = ExitStack()
        self.addCleanup(self.external.close)
        for name in ("listar_materiais_completo", "listar_regras_fiscais", "listar_usuarios",
                     "listar_logs_auditorias", "listar_logs_revisoes_preco"):
            self.external.enter_context(patch.object(database, name, return_value=[]))
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

    def test_process_action_persists_once_and_download_rerun_keeps_batch(self):
        at = self.cached_app()
        results = at.session_state["resultados_processados"][0]
        self.writes.side_effect = None
        with tempfile.TemporaryDirectory() as directory, chdir(directory), patch.object(
            parser, "processar_pdf", return_value=results
        ), patch.object(parser, "extract_order_number", return_value="4501"), patch.object(
            database, "pedido_ja_aprovado", return_value=False
        ):
            next(b for b in at.button if b.label == "Processar pedidos").click().run()
            self.assertEqual(len(at.exception), 0)
            self.assertEqual(self.writes.call_count, 1)
            self.assertEqual(self.writes.call_args.kwargs["usuario"], "Usuário de teste")
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
                at.sidebar.radio[0].set_value(menu).run()
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
        expected = {
            "ADMIN": ["📄 Análise de Pedidos KSB", "📦 Itens Cadastrados", "💰 Revisão de Preços", "🏛 Regras Fiscais", "🧾 Log", "👤 Usuários", "🛠️ Ferramentas Administrativas"],
            "VENDEDORA": ["📄 Análise de Pedidos KSB", "📦 Itens Cadastrados"],
            "PROCESSISTA": ["📦 Itens Cadastrados"],
            "OUTRO": ["📄 Análise de Pedidos KSB"],
        }
        for profile, menus in expected.items():
            with self.subTest(profile=profile):
                at = self.app(profile)
                self.assertEqual(at.sidebar.radio[0].options, menus)
                for menu in menus:
                    at.sidebar.radio[0].set_value(menu).run()
                    self.assertEqual(len(at.exception), 0, menu)
        self.assertEqual(self.writes.call_count, 0)

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
