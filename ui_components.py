"""Presentation-only components for the approved blue design system.

No database access, audit decisions or price calculations belong in this module.
All values embedded in HTML are escaped, including diagnostic text from PDFs.
"""

from html import escape
from pathlib import Path

import pandas as pd


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
    pedido = escape(texto(linha.get("Pedido")))
    item = escape(texto(linha.get("Item")))
    codigo = escape(texto(linha.get("Código Material")))
    descricao = escape(texto(linha.get("Descrição")))
    return (
        '<article class="ds-result-row">'
        '<div class="ds-result-identity">'
        f'<span class="ds-eyebrow">Pedido {pedido}</span>'
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
