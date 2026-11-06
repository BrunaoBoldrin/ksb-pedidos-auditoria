"""Presentation-only components for the approved blue design system.

No database access, audit decisions or price calculations belong in this module.
All values embedded in HTML are escaped, including diagnostic text from PDFs.
"""

from html import escape
from io import BytesIO
from pathlib import Path
from datetime import date, datetime
import unicodedata

import pandas as pd
import streamlit as st


EXCEL_BRL_NUMBER_FORMAT = '[$R$-pt-BR] #,##0.00'
MONETARY_COLUMNS = {
    "Preço Unitário Líquido",
    "Preço Pedido KSB",
    "Preço Cadastrado",
    "Preço Cadastrado c/ Imposto",
    "Preço Anterior",
    "Preço Novo",
    "Diferença Preço",
    "Valor Total",
    "Valor Unitario",
    "Valor Unitário Líquido",
    "Valor Base",
    "Valor Pedido",
    "Valor Calculado",
    "Diferença",
    "Valor ICMS",
    "Base PIS/COFINS",
    "Valor PIS",
    "Valor COFINS",
    "Valor PIS/COFINS",
    "Valor IPI",
}


def formatar_moeda_brl(valor):
    if valor is None or pd.isna(valor):
        return ""
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        texto_numero = str(valor).strip().replace("R$", "").strip()
        if "," not in texto_numero:
            return str(valor)
        try:
            numero = float(texto_numero.replace(".", "").replace(",", "."))
        except ValueError:
            return str(valor)
    formatado = f"{abs(numero):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    sinal = "-" if numero < 0 else ""
    return f"R$ {sinal}{formatado}"


def format_currency_columns(dataframe):
    table = dataframe.copy()
    for column in MONETARY_COLUMNS.intersection(table.columns):
        table[column] = table[column].map(formatar_moeda_brl)
    return table


def write_dataframe_to_excel(writer, dataframe, sheet_name):
    table = dataframe.drop(columns=["Selecionar"], errors="ignore")
    table.to_excel(writer, index=False, sheet_name=sheet_name)
    worksheet = writer.sheets[sheet_name]
    for column_index, column_name in enumerate(table.columns, start=1):
        if column_name not in MONETARY_COLUMNS:
            continue
        for row_index in range(2, len(table) + 2):
            worksheet.cell(row=row_index, column=column_index).number_format = EXCEL_BRL_NUMBER_FORMAT


@st.cache_data(show_spinner=False,max_entries=16,ttl=300)
def dataframe_to_excel_bytes(dataframe, sheet_name="Dados"):
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        write_dataframe_to_excel(writer, dataframe, sheet_name)
    return buffer.getvalue()


def texto(valor, padrao="—"):
    if valor is None or pd.isna(valor):
        return padrao
    result = str(valor).strip()
    return result if result else padrao


def _status(df, column):
    return df.get(column, pd.Series("", index=df.index)).fillna("").astype(str)


def resumo_lote(df):
    fiscal = _status(df, "Status")
    comercial = _status(df, "Status Comercial")
    approved = int(((fiscal == "OK") & (comercial == "OK")).sum())
    return {
        "total": len(df),
        "aprovados": approved,
        "pendentes": len(df) - approved,
        "revisao_preco": int((comercial == "PENDENTE - REVISÃO DE PREÇO").sum()),
        "divergencia_fiscal": int((fiscal == "DIVERGENTE").sum()),
    }


def filtrar_itens(df, filtro, pedido="Todos"):
    approved = (_status(df, "Status") == "OK") & (_status(df, "Status Comercial") == "OK")
    mask = pd.Series(True, index=df.index)
    if filtro == "Com pendência":
        mask &= ~approved
    elif filtro == "Aprovados":
        mask &= approved
    if pedido != "Todos":
        mask &= _status(df, "Pedido") == str(pedido)
    return df.loc[mask].copy()


def _normalizar_busca(valor):
    normalizado = unicodedata.normalize("NFKD", texto(valor, ""))
    return "".join(caractere for caractere in normalizado if not unicodedata.combining(caractere)).lower()


def selecionar_codigo_gloria(linha):
    unidade = _normalizar_busca(linha.get("Unidade Pedido"))
    if "jundiai" in unidade:
        return texto(linha.get("Código Interno Jundiaí"), "Não cadastrado")
    if "varzea" in unidade:
        return texto(linha.get("Código Interno Várzea"), "Não cadastrado")
    return "Unidade não identificada"


def _numero_seguro(valor):
    if valor is None or pd.isna(valor):
        return None
    if isinstance(valor, str):
        valor = valor.strip().replace("R$", "").strip()
        if not valor:
            return None
        if "," in valor:
            valor = valor.replace(".", "").replace(",", ".")
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def calcular_preco_unitario_final(linha):
    valor_total = _numero_seguro(linha.get("Valor Pedido"))
    quantidade = _numero_seguro(linha.get("Quantidade"))
    if valor_total is None or quantidade is None or quantidade <= 0:
        return None
    return round(valor_total / quantidade, 2)


def formatar_prazo_entrega(data_entrega, data_referencia=None):
    data_referencia = data_referencia or date.today()
    try:
        entrega = datetime.strptime(texto(data_entrega, ""), "%d.%m.%Y").date()
    except (TypeError, ValueError):
        return "Não disponível"

    dias = (entrega - data_referencia).days
    if dias > 0:
        return f"{dias} dia restante" if dias == 1 else f"{dias} dias restantes"
    if dias == 0:
        return "Entrega hoje"
    atraso = abs(dias)
    return f"Atrasado há {atraso} dia" if atraso == 1 else f"Atrasado há {atraso} dias"


def agrupar_pedidos(df_lote, df_visivel):
    if df_visivel.empty or "Pedido" not in df_visivel.columns:
        return []

    ordem_visivel = list(dict.fromkeys(_status(df_visivel, "Pedido").tolist()))
    status_pedidos = {}
    for pedido in ordem_visivel:
        linhas_pedido = df_lote.loc[_status(df_lote, "Pedido") == pedido]
        aprovado = (
            not linhas_pedido.empty
            and (_status(linhas_pedido, "Status") == "OK").all()
            and (_status(linhas_pedido, "Status Comercial") == "OK").all()
        )
        status_pedidos[pedido] = "OK" if aprovado else "PENDENTE"

    pedidos_ordenados = sorted(
        ordem_visivel,
        key=lambda pedido: (status_pedidos[pedido] != "OK", ordem_visivel.index(pedido)),
    )
    grupos = []
    for pedido in pedidos_ordenados:
        itens = df_visivel.loc[_status(df_visivel, "Pedido") == pedido].copy()
        itens["_ordem_item"] = pd.to_numeric(_status(itens, "Item"), errors="coerce")
        itens = itens.sort_values("_ordem_item", kind="stable", na_position="last").drop(columns="_ordem_item")
        grupos.append((pedido, status_pedidos[pedido], itens))
    return grupos


def _tom(status):
    status = texto(status, "Não avaliado")
    if status == "OK":
        return "success"
    if "PENDENTE" in status:
        return "warning"
    if status.upper().startswith(("NÃO AVALIADO", "NÃO EXECUTADO", "NAO AVALIADO")):
        return "neutral"
    return "error"


def badge_html(status):
    status = texto(status, "Não avaliado")
    tone = _tom(status)
    symbol = {"success": "✓", "warning": "!", "error": "×", "neutral": "–"}[tone]
    return (f'<span class="ds-badge ds-badge--{tone}">'
            f'<span aria-hidden="true">{symbol}</span>{escape(status)}</span>')


def cabecalho_item_html(linha):
    item = escape(texto(linha.get("Item")))
    codigo = escape(texto(linha.get("Código Material")))
    descricao = escape(texto(linha.get("Descrição")))
    return (
        '<article class="ds-result-row">'
        '<div class="ds-result-identity">'
        '<span class="ds-eyebrow">Item do pedido</span>'
        f'<strong>Item {item}</strong><span class="ds-code">{codigo}</span></div>'
        f'<div class="ds-result-description">{descricao}</div>'
        '<div class="ds-result-status"><span class="ds-label">Fiscal</span>'
        f'{badge_html(linha.get("Status"))}</div>'
        '<div class="ds-result-status"><span class="ds-label">Comercial</span>'
        f'{badge_html(linha.get("Status Comercial"))}</div></article>'
    )


def painel_diagnostico_html(etapa, status, diagnostico):
    step = "01" if etapa == "Fiscal" else "02"
    content = escape(texto(diagnostico, "Sem diagnóstico disponível.")).replace("\n", "<br>")
    return (
        f'<section class="ds-diagnostic ds-diagnostic--{_tom(status)}">'
        '<div class="ds-diagnostic-heading">'
        f'<h3>{step} · {escape(str(etapa))}</h3>{badge_html(status)}</div>'
        f'<p>{content}</p></section>'
    )


def page_header_html(titulo, descricao):
    return ('<header class="ds-page-header"><p class="ds-eyebrow">ANALISADOR DE PEDIDOS KSB</p>'
            f'<h1>{escape(str(titulo))}</h1><p>{escape(str(descricao))}</p></header>')


def profile_html(nome, perfil):
    name = texto(nome, "Usuário")
    initials = "".join(part[0] for part in name.split()[:2]).upper()
    return ('<div class="ds-profile">'
            f'<span class="ds-avatar">{escape(initials)}</span><div>'
            f'<strong>{escape(name)}</strong><span>{escape(texto(perfil))}</span>'
            '</div></div>')


def metric_html(label, value, detalhe="", destaque=False):
    variant = " ds-metric--brand" if destaque else ""
    return (f'<div class="ds-metric{variant}"><span>{escape(str(label))}</span>'
            f'<strong>{escape(str(value))}</strong><small>{escape(str(detalhe))}</small></div>')


def apply_design():
    import streamlit as st

    assets = Path(__file__).with_name("assets")
    tokens = (assets / "design-tokens.css").read_text(encoding="utf-8")
    styles = (assets / "design-system.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{tokens}\n{styles}</style>", unsafe_allow_html=True)


def page_header(titulo, descricao):
    import streamlit as st

    st.markdown(page_header_html(titulo, descricao), unsafe_allow_html=True)


def render_summary(df):
    import streamlit as st

    summary = resumo_lote(df)
    cards = (
        ("Itens analisados", summary["total"], "No lote atual", False),
        ("Itens aprovados", summary["aprovados"], "Fiscal e comercial OK", True),
        ("Revisão de preço", summary["revisao_preco"], "Ação necessária", False),
        ("Com pendência", summary["pendentes"], f'{summary["divergencia_fiscal"]} com divergência fiscal', False),
    )
    for col, values in zip(st.columns(4), cards):
        with col:
            st.markdown(metric_html(*values), unsafe_allow_html=True)
