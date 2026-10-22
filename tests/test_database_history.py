import unittest
from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import patch

import database


class FakeCursor:
    def __init__(self, fetchone_values=None, fetchall_value=None, update_rowcount=1):
        self.executions = []
        self.fetchone_values = list(fetchone_values or [])
        self.fetchall_value = list(fetchall_value or [])
        self.rowcount = 1
        self.update_rowcount = update_rowcount

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split())
        self.executions.append((normalized, params))
        if normalized.startswith("UPDATE materiais"):
            self.rowcount = self.update_rowcount

    def fetchone(self):
        return self.fetchone_values.pop(0) if self.fetchone_values else None

    def fetchall(self):
        return self.fetchall_value


def cursor_context(cursor):
    @contextmanager
    def fake_cursor(commit=False):
        yield cursor

    return fake_cursor


class DatabaseMigrationTests(unittest.TestCase):
    def test_initialization_adds_idempotent_audit_and_price_history_schema(self):
        cursor = FakeCursor()
        with patch.object(database, "_cursor", cursor_context(cursor)), patch.object(
            database, "inserir_usuario"
        ):
            database.inicializar_banco()

        sql = "\n".join(statement for statement, _ in cursor.executions)
        self.assertIn("ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS usuario_auditoria", sql)
        self.assertIn("ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS tipo_execucao", sql)
        self.assertIn("ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS confirmou_auditoria", sql)
        self.assertIn("ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS confirmou_implantacao", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS revisoes_preco", sql)
        revision_schema = sql.split("CREATE TABLE IF NOT EXISTS revisoes_preco", 1)[1]
        self.assertNotIn("REFERENCES materiais", revision_schema.split("CREATE TABLE", 1)[0])


class DatabaseRepositoryTests(unittest.TestCase):
    def material_args(self, price):
        return (
            "WGS-5520",
            "Peça teste",
            "LATÃO",
            "BRN 66",
            "7419.80.90",
            "PEÇ",
            "J-1",
            "V-1",
            price,
            "2026-10-22",
            "Administrador",
        )

    def revision_inserts(self, cursor):
        return [entry for entry in cursor.executions if "INSERT INTO revisoes_preco" in entry[0]]

    def test_detects_any_previously_approved_audit(self):
        cursor = FakeCursor(fetchone_values=[(True,)])
        with patch.object(database, "_cursor", cursor_context(cursor)):
            self.assertTrue(database.pedido_ja_aprovado("4508000000"))

        query, params = cursor.executions[0]
        self.assertIn("status_etapa1 = 'OK'", query)
        self.assertIn("status_etapa2 = 'OK'", query)
        self.assertEqual(params, ("4508000000",))

    def test_manual_price_change_creates_revision_log(self):
        cursor = FakeCursor(fetchone_values=[("Peça teste", 100.0)])
        with patch.object(database, "_cursor", cursor_context(cursor)):
            database.atualizar_material(*self.material_args(120.0))

        inserts = self.revision_inserts(cursor)
        self.assertEqual(len(inserts), 1)
        self.assertEqual(inserts[0][1][0:4], ("WGS-5520", "Peça teste", Decimal("100.00"), Decimal("120.00")))
        self.assertEqual(inserts[0][1][-1], "ALTERAÇÃO PELO SISTEMA")

    def test_excel_price_change_records_excel_origin(self):
        cursor = FakeCursor(fetchone_values=[("Peça teste", 100.0)])
        with patch.object(database, "_cursor", cursor_context(cursor)):
            database.atualizar_material(*self.material_args(120.0), origem_alteracao="IMPORTAÇÃO EXCEL")

        self.assertEqual(self.revision_inserts(cursor)[0][1][-1], "IMPORTAÇÃO EXCEL")

    def test_equal_cent_value_does_not_create_revision_log(self):
        cursor = FakeCursor(fetchone_values=[("Peça teste", 100.0)])
        with patch.object(database, "_cursor", cursor_context(cursor)):
            database.atualizar_material(*self.material_args(100.004))

        self.assertEqual(self.revision_inserts(cursor), [])

    def test_omitted_price_does_not_create_revision_log(self):
        cursor = FakeCursor(fetchone_values=[("Peça teste", 100.0)])
        with patch.object(database, "_cursor", cursor_context(cursor)):
            database.atualizar_material(*self.material_args(None))

        self.assertEqual(self.revision_inserts(cursor), [])

    def test_initial_material_insert_does_not_create_revision_log(self):
        cursor = FakeCursor(fetchone_values=[None], update_rowcount=0)
        with patch.object(database, "_cursor", cursor_context(cursor)):
            database.atualizar_material(*self.material_args(100.0))

        self.assertEqual(self.revision_inserts(cursor), [])

    def test_registers_order_items_and_item_audits_in_one_transaction(self):
        cursor = FakeCursor(fetchone_values=[(101,), (201,)])
        order = {
            "Pedido": "4508000000",
            "Data Emissão": "30.06.2026",
            "Comprador": "Comprador Teste",
            "Unidade Pedido": "Várzea",
        }
        items = [
            {
                "Item": "00010",
                "Código Material": "WGS-5520",
                "Descrição": "Peça teste",
                "Quantidade": 1.0,
                "Unidade": "PEÇ",
                "Data Entrega": "25.09.2026",
                "Preço Pedido KSB": 120.0,
                "Valor Pedido": 120.0,
                "Material": "LATÃO",
                "Norma": "BRN 66",
                "NCM Pedido KSB": "7419.80.90",
                "Leadtime Dias": 10,
                "Status": "OK",
                "Diagnóstico": "ANÁLISE FISCAL OK",
                "Status Comercial": "OK",
                "Diagnóstico Comercial": "PREÇO OK",
                "Preço Cadastrado": 120.0,
                "Diferença Preço": 0.0,
            }
        ]
        with patch.object(database, "_cursor", cursor_context(cursor)):
            pedido_id = database.registrar_auditoria_pedido(
                order, items, "Administrador", False, False, False, "pedido.pdf"
            )

        self.assertEqual(pedido_id, 101)
        sql = "\n".join(statement for statement, _ in cursor.executions)
        self.assertIn("INSERT INTO pedidos", sql)
        self.assertIn("INSERT INTO pedido_itens", sql)
        self.assertIn("INSERT INTO auditorias", sql)

    def test_repository_error_is_propagated(self):
        class FailingCursor(FakeCursor):
            def execute(self, sql, params=None):
                if "INSERT INTO pedido_itens" in sql:
                    raise RuntimeError("falha de gravação")
                super().execute(sql, params)

        cursor = FailingCursor(fetchone_values=[(101,)])
        with patch.object(database, "_cursor", cursor_context(cursor)):
            with self.assertRaisesRegex(RuntimeError, "falha de gravação"):
                database.registrar_auditoria_pedido(
                    {"Pedido": "1"},
                    [{"Status": "OK", "Status Comercial": "OK"}],
                    "Administrador",
                    False,
                    False,
                    False,
                    "pedido.pdf",
                )


if __name__ == "__main__":
    unittest.main()
