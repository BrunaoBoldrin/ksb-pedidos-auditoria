import unittest
from datetime import date

import pandas as pd

from ui_rules import (
    build_outdated_prices_table,
    filter_audit_log,
    filter_price_log,
    format_timestamp_sao_paulo,
    menu_options_for_profile,
)


def material_row(code, description, price, review_date, user="Admin"):
    return (
        code,
        description,
        "LATÃO",
        "BRN 66",
        "7419.80.90",
        "PEÇ",
        "J-1",
        "V-1",
        price,
        review_date,
        user,
    )


class AdminViewRulesTests(unittest.TestCase):
    def test_admin_only_receives_new_price_review_and_log_menus(self):
        admin = menu_options_for_profile("ADMIN")
        self.assertIn("💰 Revisão de Preços", admin)
        self.assertIn("🧾 Log", admin)
        self.assertIn("⚙️ Configurações", admin)

        for profile in ("VENDEDORA", "PROCESSISTA", "OUTRO"):
            with self.subTest(profile=profile):
                options = menu_options_for_profile(profile)
                self.assertNotIn("💰 Revisão de Preços", options)
                self.assertNotIn("🧾 Log", options)
                self.assertNotIn("⚙️ Configurações", options)

    def test_setting_timestamp_is_displayed_in_sao_paulo_time(self):
        self.assertEqual(
            format_timestamp_sao_paulo("2026-10-23T17:44:51+00:00"),
            "23/10/2026 14:44:51",
        )

    def test_legacy_audit_history_menu_is_removed_for_every_profile(self):
        for profile in ("ADMIN", "VENDEDORA", "PROCESSISTA", "OUTRO"):
            with self.subTest(profile=profile):
                self.assertNotIn("📋 Histórico de Auditorias", menu_options_for_profile(profile))

    def test_outdated_table_excludes_valid_and_missing_prices(self):
        rows = [
            material_row("SEM-DATA", "Sem data", 100.0, ""),
            material_row("ANTIGO", "Preço antigo", 100.0, "2026-01-01"),
            material_row("VALIDO", "Preço válido", 100.0, "2026-08-01"),
            material_row("SEM-PRECO", "Sem preço", 0.0, "2026-01-01"),
        ]

        table = build_outdated_prices_table(rows, date(2026, 10, 22))

        self.assertEqual(table["Código Material"].tolist(), ["SEM-DATA", "ANTIGO"])
        self.assertEqual(table.iloc[0]["Situação"], "Sem data de revisão")
        self.assertEqual(table.iloc[1]["Situação"], "Revisão vencida")

    def test_outdated_table_uses_custom_review_period(self):
        rows = [material_row("RECENTE", "Preço recente", 100.0, "2026-09-01")]

        table = build_outdated_prices_table(rows, date(2026, 10, 22), review_days=30)

        self.assertEqual(table["Código Material"].tolist(), ["RECENTE"])

    def test_log_filters_apply_query_user_and_period(self):
        audit_df = pd.DataFrame(
            [
                ["4501", "PRIMEIRA ANÁLISE", "OK", "OK", "Ana", "2026-10-10"],
                ["4502", "REAVALIAÇÃO", "OK", "PENDENTE/DIVERGENTE", "Bruno", "2026-10-20"],
            ],
            columns=["Pedido", "Tipo", "Fiscal", "Comercial", "Usuário", "Data/Hora"],
        )
        price_df = pd.DataFrame(
            [
                ["WGS-5520", "Peça", 100.0, 120.0, "Ana", "2026-10-10", "ALTERAÇÃO PELO SISTEMA"],
                ["02154693", "Outra", 50.0, 55.0, "Bruno", "2026-10-20", "IMPORTAÇÃO EXCEL"],
            ],
            columns=["Código Material", "Descrição", "Preço Anterior", "Preço Novo", "Usuário", "Data/Hora", "Origem"],
        )

        audits = filter_audit_log(audit_df, "4502", "Bruno", date(2026, 10, 15), date(2026, 10, 22))
        prices = filter_price_log(price_df, "WGS", "Ana", date(2026, 10, 1), date(2026, 10, 15))

        self.assertEqual(audits["Pedido"].tolist(), ["4502"])
        self.assertEqual(prices["Código Material"].tolist(), ["WGS-5520"])

    def test_log_query_treats_regex_characters_as_literal_text(self):
        price_df = pd.DataFrame(
            [["WGS-[5520]", "Peça", 100.0, 120.0, "Ana", "2026-10-10", "ALTERAÇÃO PELO SISTEMA"]],
            columns=["Código Material", "Descrição", "Preço Anterior", "Preço Novo", "Usuário", "Data/Hora", "Origem"],
        )

        prices = filter_price_log(price_df, "[", "Todos", None, None)

        self.assertEqual(prices["Código Material"].tolist(), ["WGS-[5520]"])

    def test_log_displays_utc_timestamp_in_sao_paulo_time(self):
        audit_df = pd.DataFrame(
            [["4501", "PRIMEIRA ANÁLISE", "OK", "OK", "Ana", "2026-10-23T17:44:51+00:00"]],
            columns=["Pedido", "Tipo", "Fiscal", "Comercial", "Usuário", "Data/Hora"],
        )

        audits = filter_audit_log(audit_df)

        self.assertEqual(audits.iloc[0]["Data/Hora"], "23/10/2026 14:44:51")

    def test_log_period_filter_uses_sao_paulo_calendar_date(self):
        audit_df = pd.DataFrame(
            [["4501", "PRIMEIRA ANÁLISE", "OK", "OK", "Ana", "2026-10-23T01:30:00+00:00"]],
            columns=["Pedido", "Tipo", "Fiscal", "Comercial", "Usuário", "Data/Hora"],
        )

        audits = filter_audit_log(
            audit_df,
            start=date(2026, 10, 22),
            end=date(2026, 10, 22),
        )

        self.assertEqual(audits["Pedido"].tolist(), ["4501"])
        self.assertEqual(audits.iloc[0]["Data/Hora"], "22/10/2026 22:30:00")


if __name__ == "__main__":
    unittest.main()
