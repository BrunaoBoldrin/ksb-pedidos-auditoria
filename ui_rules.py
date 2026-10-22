"""Transformações puras usadas pelas telas administrativas Streamlit."""

import pandas as pd

from price_rules import is_price_outdated, parse_review_date


MATERIAL_COLUMNS = [
    "Código Material",
    "Descrição",
    "Material",
    "Norma",
    "NCM",
    "Unidade",
    "Código Interno Jundiaí",
    "Código Interno Várzea",
    "Preço Unitário Líquido",
    "Última Revisão",
    "Usuário Última Revisão",
]


def menu_options_for_profile(profile):
    if profile == "ADMIN":
        return [
            "📄 Análise de Pedidos KSB",
            "📦 Itens Cadastrados",
            "💰 Revisão de Preços",
            "🏛 Regras Fiscais",
            "📋 Histórico de Auditorias",
            "🧾 Log",
            "👤 Usuários",
            "🛠️ Ferramentas Administrativas",
        ]
    if profile == "VENDEDORA":
        return ["📄 Análise de Pedidos KSB", "📦 Itens Cadastrados", "📋 Histórico de Auditorias"]
    if profile == "PROCESSISTA":
        return ["📦 Itens Cadastrados"]
    return ["📄 Análise de Pedidos KSB"]


def build_outdated_prices_table(material_rows, today):
    records = []
    for row in material_rows:
        values = dict(zip(MATERIAL_COLUMNS, row))
        try:
            price = float(values.get("Preço Unitário Líquido") or 0)
        except (TypeError, ValueError):
            price = 0.0
        if price <= 0 or not is_price_outdated(values.get("Última Revisão"), today):
            continue

        parsed_date = parse_review_date(values.get("Última Revisão"))
        records.append(
            {
                "Código Material": values.get("Código Material", ""),
                "Descrição": values.get("Descrição", ""),
                "Preço Unitário Líquido": price,
                "Última Revisão": parsed_date.isoformat() if parsed_date else "",
                "Usuário Última Revisão": values.get("Usuário Última Revisão", ""),
                "Situação": "Revisão vencida" if parsed_date else "Sem data de revisão",
                "_sem_data": parsed_date is None,
                "_data_ordem": parsed_date,
            }
        )

    columns = [
        "Código Material",
        "Descrição",
        "Preço Unitário Líquido",
        "Última Revisão",
        "Usuário Última Revisão",
        "Situação",
    ]
    if not records:
        return pd.DataFrame(columns=columns)

    table = pd.DataFrame(records)
    table = table.sort_values(
        by=["_sem_data", "_data_ordem", "Código Material"],
        ascending=[False, True, True],
        na_position="first",
    )
    return table[columns].reset_index(drop=True)


def _filter_log(dataframe, query, user, start, end, searchable_columns):
    result = dataframe.copy()
    if result.empty:
        return result

    query = str(query or "").strip()
    if query:
        matches = pd.Series(False, index=result.index)
        for column in searchable_columns:
            if column in result.columns:
                matches |= result[column].astype(str).str.contains(
                    query,
                    case=False,
                    na=False,
                    regex=False,
                )
        result = result[matches]

    user = str(user or "").strip()
    if user and user != "Todos" and "Usuário" in result.columns:
        result = result[result["Usuário"].astype(str) == user]

    if "Data/Hora" in result.columns:
        timestamps = pd.to_datetime(result["Data/Hora"], errors="coerce")
        if start is not None:
            result = result[timestamps.dt.date >= start]
            timestamps = pd.to_datetime(result["Data/Hora"], errors="coerce")
        if end is not None:
            result = result[timestamps.dt.date <= end]

    return result.reset_index(drop=True)


def filter_audit_log(dataframe, query="", user="Todos", start=None, end=None):
    return _filter_log(dataframe, query, user, start, end, ["Pedido", "Tipo"])


def filter_price_log(dataframe, query="", user="Todos", start=None, end=None):
    return _filter_log(dataframe, query, user, start, end, ["Código Material", "Descrição", "Origem"])
