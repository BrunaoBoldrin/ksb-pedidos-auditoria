import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch

import database
from system_settings import SystemSettings


class FakeCursor:
    def __init__(self, rows=None):
        self.executions = []
        self.rows = list(rows or [])

    def execute(self, sql, params=None):
        self.executions.append((" ".join(sql.split()), params))

    def fetchall(self):
        return self.rows


def cursor_context(cursor):
    @contextmanager
    def fake_cursor(commit=False):
        yield cursor

    return fake_cursor


class DatabaseSettingsTests(unittest.TestCase):
    def test_initialization_creates_and_seeds_settings_idempotently(self):
        cursor = FakeCursor()
        with patch.object(database, "_cursor", cursor_context(cursor)), patch.object(
            database, "inserir_usuario"
        ):
            database.inicializar_banco()

        sql = "\n".join(statement for statement, _ in cursor.executions)
        self.assertIn("CREATE TABLE IF NOT EXISTS configuracoes_sistema", sql)
        self.assertEqual(sql.count("ON CONFLICT (chave) DO NOTHING"), 3)

    def test_missing_database_rows_return_safe_defaults(self):
        loader = getattr(database, "buscar_configuracoes_sistema", None)
        self.assertTrue(callable(loader), "O repositório deve carregar configurações")
        cursor = FakeCursor()
        with patch.object(database, "_cursor", cursor_context(cursor)):
            settings = loader()

        self.assertEqual(settings, SystemSettings())

    def test_saved_rows_are_normalized_into_settings(self):
        loader = getattr(database, "buscar_configuracoes_sistema", None)
        self.assertTrue(callable(loader), "O repositório deve carregar configurações")
        cursor = FakeCursor([
            ("price_review_days", "120"),
            ("price_difference_tolerance", "0.5"),
            ("fiscal_difference_tolerance", "2.75"),
        ])
        with patch.object(database, "_cursor", cursor_context(cursor)):
            settings = loader()

        self.assertEqual(settings, SystemSettings(120, 0.5, 2.75))

    def test_save_updates_all_settings_in_one_transaction_with_user(self):
        saver = getattr(database, "salvar_configuracoes_sistema", None)
        self.assertTrue(callable(saver), "O repositório deve salvar configurações")
        cursor = FakeCursor()
        with patch.object(database, "_cursor", cursor_context(cursor)):
            saver(SystemSettings(180, 0.25, 3.0), "Administrador")

        upserts = [entry for entry in cursor.executions if "INSERT INTO configuracoes_sistema" in entry[0]]
        self.assertEqual(len(upserts), 3)
        self.assertEqual({params[0] for _, params in upserts}, {
            "price_review_days",
            "price_difference_tolerance",
            "fiscal_difference_tolerance",
        })
        self.assertTrue(all(params[2] == "Administrador" for _, params in upserts))

    def test_metadata_is_returned_by_setting_key(self):
        loader = getattr(database, "listar_metadados_configuracoes", None)
        self.assertTrue(callable(loader), "O repositório deve expor metadados das configurações")
        changed_at = datetime(2026, 10, 27, 14, 30, tzinfo=timezone.utc)
        cursor = FakeCursor([("price_review_days", "Administrador", changed_at)])
        with patch.object(database, "_cursor", cursor_context(cursor)):
            metadata = loader()

        self.assertEqual(metadata["price_review_days"]["usuario"], "Administrador")
        self.assertEqual(metadata["price_review_days"]["data_hora"], changed_at)


if __name__ == "__main__":
    unittest.main()
