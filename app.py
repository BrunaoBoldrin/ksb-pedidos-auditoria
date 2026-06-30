from datetime import date
from html import escape
from io import BytesIO
import re

import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from database import (
    atualizar_material,
    atualizar_regra_fiscal,
    buscar_material,
    buscar_usuario_login,
    conectar,
    excluir_material,
    excluir_regra_fiscal,
    excluir_usuario,
    inserir_material,
    inserir_regra_fiscal,
    inserir_usuario,
    listar_materiais_completo,
    listar_regras_fiscais,
    listar_usuarios,
)
from parser import processar_pdf

st.set_page_config(page_title="Analisador de Pedidos", page_icon="📄", layout="wide")

st.markdown(
    """
<style>
.stButton button {width: 100%; height: 48px; font-weight: bold;}
</style>
""",
    unsafe_allow_html=True,
)



def formatar_moeda(valor):
    try:
        return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "-"


def valor_texto(linha, coluna, padrao="-"):
    valor = linha.get(coluna, padrao)
    if pd.isna(valor) or str(valor).strip() in ["", "nan", "None"]:
        return padrao
    return str(valor)


def texto_pdf(valor):
    return escape(str(valor_texto({"v": valor}, "v")))


def pedidos_unicos(df_analise):
    if "Pedido" not in df_analise.columns:
        return []
    pedidos = []
    for pedido in df_analise["Pedido"].dropna():
        pedido_texto = valor_texto({"Pedido": pedido}, "Pedido", "")
        if pedido_texto and pedido_texto not in pedidos:
            pedidos.append(pedido_texto)
    return pedidos


def titulo_avaliacao_pedidos(df_analise):
    pedidos = pedidos_unicos(df_analise)
    if not pedidos:
        return "Avaliação do Pedido sem código"
    if len(pedidos) == 1:
        return f"Avaliação do Pedido {pedidos[0]}"
    return f"Avaliação dos Pedidos {' - '.join(pedidos)}"


def gerar_pdf_auditoria(df_analise, codigo_pedido=None):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=28, leftMargin=28, topMargin=28, bottomMargin=28)
    styles = getSampleStyleSheet()
    elementos = []
    titulo_pedidos = titulo_avaliacao_pedidos(df_analise)
    total = len(df_analise)
    ok = len(df_analise[df_analise["Status"] == "OK"]) if "Status" in df_analise.columns else 0
    divergentes = len(df_analise[df_analise["Status"] == "DIVERGENTE"]) if "Status" in df_analise.columns else 0
    primeira = df_analise.iloc[0] if total else {}

    elementos.append(Paragraph(texto_pdf(titulo_pedidos), styles["Title"]))
    elementos.append(Paragraph(f"Data de emissão: {texto_pdf(valor_texto(primeira, 'Data Emissão'))} | Unidade: {texto_pdf(valor_texto(primeira, 'Unidade Pedido'))} | Comprador: {texto_pdf(valor_texto(primeira, 'Comprador'))}", styles["Normal"]))
    elementos.append(Spacer(1, 10))
    resumo = Table([["Itens analisados", "OK", "Divergentes"], [total, ok, divergentes]], hAlign="LEFT")
    resumo.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey), ("GRID", (0, 0), (-1, -1), 0.5, colors.grey)]))
    elementos.extend([resumo, Spacer(1, 12)])

    for _, linha in df_analise.iterrows():
        status = valor_texto(linha, "Status")
        titulo = f"Pedido {valor_texto(linha, 'Pedido')} - Item {valor_texto(linha, 'Item')} - Material {valor_texto(linha, 'Código Material')} - {status}"
        elementos.append(Paragraph(texto_pdf(titulo), styles["Heading3"]))
        dados = [
            ["Descrição", valor_texto(linha, "Descrição")],
            ["Qtd/Unidade", f"{valor_texto(linha, 'Quantidade')} {valor_texto(linha, 'Unidade')}"] ,
            ["NCM Pedido", valor_texto(linha, "NCM Pedido KSB")],
            ["NCM Cadastro", valor_texto(linha, "NCM Cadastro")],
            ["Impostos", f"ICMS {valor_texto(linha, 'ICMS Regra')}% — {formatar_moeda(linha.get('Valor ICMS'))} | PIS/COFINS 9,25% — {formatar_moeda(linha.get('Valor PIS/COFINS'))} | IPI {valor_texto(linha, 'IPI Regra')}% — {formatar_moeda(linha.get('Valor IPI'))}"],
            ["Valores", f"Líquido unitário {formatar_moeda(linha.get('Valor Unitário Líquido'))} | Base {formatar_moeda(linha.get('Valor Base'))} | Pedido {formatar_moeda(linha.get('Valor Pedido'))} | Diferença {formatar_moeda(linha.get('Diferença'))}"],
            ["Pedido x Calculado", f"Pedido {formatar_moeda(linha.get('Valor Pedido'))} | Calculado {formatar_moeda(linha.get('Valor Calculado'))} | Diferença {formatar_moeda(linha.get('Diferença'))}"],
            ["Diagnóstico", valor_texto(linha, "Diagnóstico")],
        ]
        campos_longos = {"Descrição", "Impostos", "Valores", "Pedido x Calculado", "Diagnóstico"}
        dados = [
            [
                texto_pdf(rotulo),
                Paragraph(
                    texto_pdf(valor).replace(" | ", "<br/>") if rotulo in campos_longos else texto_pdf(valor),
                    styles["BodyText"],
                ),
            ]
            for rotulo, valor in dados
        ]
        tabela = Table(dados, colWidths=[105, 395])
        tabela.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke)]))
        elementos.extend([tabela, Spacer(1, 10)])

    doc.build(elementos)
    buffer.seek(0)
    return buffer.getvalue()


def exibir_cards_auditoria(df_analise_final):
    total = len(df_analise_final)
    ok = len(df_analise_final[df_analise_final["Status"] == "OK"])
    divergentes = len(df_analise_final[df_analise_final["Status"] == "DIVERGENTE"])
    col1, col2, col3 = st.columns(3)
    col1.metric("Itens Processados", total)
    col2.metric("Itens OK", ok)
    col3.metric("Itens Divergentes", divergentes)
    st.divider()
    st.subheader("📋 Auditoria detalhada por item")
    for _, linha in df_analise_final.iterrows():
        status = valor_texto(linha, "Status")
        cor = "#0f8a3b" if status == "OK" else "#b42318"
        with st.container(border=True):
            st.markdown(f"### <span style='color:{cor}'>{'✅' if status == 'OK' else '❌'} {status}</span> — Pedido {valor_texto(linha, 'Pedido')} | Item {valor_texto(linha, 'Item')} | Material {valor_texto(linha, 'Código Material')}", unsafe_allow_html=True)
            c1, c2, c3 = st.columns(3)
            c1.write(f"**Descrição:** {valor_texto(linha, 'Descrição')}")
            c1.write(f"**Quantidade:** {valor_texto(linha, 'Quantidade')} {valor_texto(linha, 'Unidade')}")
            c2.write(f"**NCM Pedido:** {valor_texto(linha, 'NCM Pedido KSB')}")
            c2.write(f"**NCM Cadastro:** {valor_texto(linha, 'NCM Cadastro')}")
            c3.write(f"**ICMS:** {valor_texto(linha, 'ICMS Regra')}% — {formatar_moeda(linha.get('Valor ICMS'))}")
            c3.write(f"**PIS/COFINS:** 9,25% — {formatar_moeda(linha.get('Valor PIS/COFINS'))}")
            c3.write(f"**IPI:** {valor_texto(linha, 'IPI Regra')}% — {formatar_moeda(linha.get('Valor IPI'))}")
            v1, v2, v3, v4 = st.columns(4)
            v1.metric("Líquido Unitário", formatar_moeda(linha.get("Valor Unitário Líquido")))
            v2.metric("Valor Base", formatar_moeda(linha.get("Valor Base")))
            v3.metric("Valor Pedido", formatar_moeda(linha.get("Valor Pedido")))
            v4.metric("Diferença", formatar_moeda(linha.get("Diferença")))
            if status != "OK":
                st.error(f"**Diagnóstico:** {valor_texto(linha, 'Diagnóstico')}")
                if valor_texto(linha, "Descrição NCM Pedido", ""):
                    st.caption(f"NCM do pedido: {valor_texto(linha, 'NCM Pedido KSB')} - {valor_texto(linha, 'Descrição NCM Pedido')}")
                    st.caption(f"NCM correto: {valor_texto(linha, 'NCM Cadastro')} - {valor_texto(linha, 'Descrição NCM Cadastro')}")


def exibir_cards_comercial(df_analise_final):
    if "Status Comercial" not in df_analise_final.columns:
        return

    st.divider()
    st.subheader("💼 Etapa 2 — Análise Comercial")

    total = len(df_analise_final)
    ok = len(df_analise_final[df_analise_final["Status Comercial"] == "OK"])
    pendentes_revisao = len(df_analise_final[df_analise_final["Status Comercial"] == "PENDENTE - REVISÃO DE PREÇO"])
    pendentes_cadastro_preco = len(
        df_analise_final[
            df_analise_final["Status Comercial"].isin(
                ["PENDENTE - MATERIAL SEM CADASTRO", "PENDENTE - PREÇO NÃO CADASTRADO"]
            )
        ]
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Itens analisados", total)
    c2.metric("Itens OK", ok)
    c3.metric("Pendentes revisão de preço", pendentes_revisao)
    c4.metric("Pendentes cadastro/preço", pendentes_cadastro_preco)

    for _, linha in df_analise_final.iterrows():
        status = valor_texto(linha, "Status Comercial")
        if status == "OK":
            cor = "#0f8a3b"
            icone = "✅"
        elif status == "PENDENTE - REVISÃO DE PREÇO":
            cor = "#b7791f"
            icone = "⚠️"
        else:
            cor = "#b42318"
            icone = "❌"

        with st.container(border=True):
            st.markdown(
                f"### <span style='color:{cor}'>{icone} Pedido {valor_texto(linha, 'Pedido')} | "
                f"Item {valor_texto(linha, 'Item')} | Material {valor_texto(linha, 'Código Material')} | {status}</span>",
                unsafe_allow_html=True,
            )
            st.write(f"**Descrição:** {valor_texto(linha, 'Descrição')}")
            p1, p2, p3, p4 = st.columns(4)
            p1.metric("Preço Pedido KSB", formatar_moeda(linha.get("Preço Pedido KSB")))
            p2.metric("Preço Cadastrado", formatar_moeda(linha.get("Preço Cadastrado")))
            p3.metric("Diferença Preço", formatar_moeda(linha.get("Diferença Preço")))
            p4.metric("Percentual Diferença", f"{valor_texto(linha, 'Percentual Diferença Preço')}%")

            l1, l2, l3 = st.columns(3)
            l1.metric("Leadtime Dias", valor_texto(linha, "Leadtime Dias"))
            l2.write(f"**Última Revisão Preço:** {valor_texto(linha, 'Data Última Revisão Preço')}")
            l3.write(f"**Usuário Última Revisão Preço:** {valor_texto(linha, 'Usuário Última Revisão Preço')}")

            diagnostico = valor_texto(linha, "Diagnóstico Comercial")
            if status == "OK":
                st.success(f"**Diagnóstico Comercial:** {diagnostico}")
            elif status == "PENDENTE - REVISÃO DE PREÇO":
                st.warning(f"**Diagnóstico Comercial:** {diagnostico}")
            else:
                st.error(f"**Diagnóstico Comercial:** {diagnostico}")


def limpar_texto(valor):
    if pd.isna(valor):
        return ""
    texto = str(valor).strip()
    if texto.lower() in ["nan", "none", "nat"]:
        return ""
    return texto


def normalizar_coluna(nome):
    nome = str(nome).replace("\n", " ").replace("\r", " ").strip().lower()
    nome = re.sub(r"\s+", " ", nome)
    troca = str.maketrans("áàãâäéèêëíìîïóòõôöúùûüç", "aaaaaeeeeiiiiooooouuuuc")
    return nome.translate(troca)


def moeda_para_float_importacao(valor):
    texto = limpar_texto(valor)
    if not texto or texto == "-":
        return 0.0
    texto = texto.replace("R$", "").replace(" ", "").strip()
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except Exception:
        return 0.0


def preparar_planilha_materiais(arquivo_excel):
    abas = pd.read_excel(arquivo_excel, sheet_name=None, dtype=str)
    partes = []
    relatorio_abas = []

    aliases = {
        "codigo": ["codigo material", "cod material", "codigo_material", "código material"],
        "descricao": ["descricao", "descrição"],
        "material": ["material"],
        "norma": ["norma"],
        "ncm": ["ncm"],
        "unidade": ["unidade"],
        "jundiai": ["codigo interno jundiai", "código interno jundiaí", "codigo interno jundiaí"],
        "varzea": ["codigo interno varzea", "código interno várzea", "codigo interno várzea"],
        "preco": ["preco unitario liquido", "preço unitário líquido", "preco revisado", "preço revisado"],
    }

    for nome_aba, df in abas.items():
        if df.empty:
            continue

        df = df.dropna(how="all").copy()
        mapa = {normalizar_coluna(col): col for col in df.columns}

        def achar(campo):
            for candidato in aliases[campo]:
                chave = normalizar_coluna(candidato)
                if chave in mapa:
                    return mapa[chave]
            return None

        colunas = {campo: achar(campo) for campo in aliases}

        if not colunas["codigo"] or not colunas["descricao"]:
            relatorio_abas.append(f"{nome_aba}: ignorada, sem cabeçalho de Código Material/Descrição")
            continue

        dados = pd.DataFrame()
        dados["Código Material"] = df[colunas["codigo"]].apply(limpar_texto)
        dados["Descrição"] = df[colunas["descricao"]].apply(limpar_texto)
        dados["Material"] = df[colunas["material"]].apply(limpar_texto) if colunas["material"] else ""
        dados["Norma"] = df[colunas["norma"]].apply(limpar_texto) if colunas["norma"] else ""
        dados["NCM"] = df[colunas["ncm"]].apply(limpar_texto) if colunas["ncm"] else ""
        dados["Unidade"] = df[colunas["unidade"]].apply(limpar_texto) if colunas["unidade"] else ""
        dados["Código Interno Jundiaí"] = df[colunas["jundiai"]].apply(limpar_texto) if colunas["jundiai"] else ""
        dados["Código Interno Várzea"] = df[colunas["varzea"]].apply(limpar_texto) if colunas["varzea"] else ""
        dados["Preço Unitário Líquido"] = df[colunas["preco"]].apply(moeda_para_float_importacao) if colunas["preco"] else 0.0
        dados = dados[dados["Código Material"] != ""]

        if not dados.empty:
            partes.append(dados)
            relatorio_abas.append(f"{nome_aba}: {len(dados)} linha(s) válida(s)")

    if not partes:
        return pd.DataFrame(), relatorio_abas

    final = pd.concat(partes, ignore_index=True)
    final = final.drop_duplicates(subset=["Código Material"], keep="last")
    return final, relatorio_abas


for chave in ["usuario_logado", "nome_usuario", "perfil_usuario"]:
    if chave not in st.session_state:
        st.session_state[chave] = None

if st.session_state.usuario_logado is None:
    st.title("🔐 Login")
    usuario = st.text_input("Usuário")
    senha = st.text_input("Senha", type="password")
    if st.button("Entrar"):
        resultado = buscar_usuario_login(usuario, senha)
        if resultado:
            st.session_state.usuario_logado = resultado[2]
            st.session_state.nome_usuario = resultado[1]
            st.session_state.perfil_usuario = resultado[3]
            st.rerun()
        else:
            st.error("Usuário ou senha inválidos")
    st.stop()

perfil = st.session_state.perfil_usuario
usuario_revisao_atual = st.session_state.nome_usuario or st.session_state.usuario_logado

with st.sidebar:
    st.success(f"👤 {st.session_state.nome_usuario}")
    st.caption(f"Perfil: {perfil}")
    if st.button("🚪 Logout"):
        st.session_state.usuario_logado = None
        st.session_state.nome_usuario = None
        st.session_state.perfil_usuario = None
        st.rerun()

if perfil == "ADMIN":
    opcoes_menu = ["📄 Análise de Pedidos KSB", "📦 Itens Cadastrados", "🏛 Regras Fiscais", "📋 Histórico de Auditorias", "👤 Usuários", "🛠️ Ferramentas Administrativas"]
elif perfil == "VENDEDORA":
    opcoes_menu = ["📄 Análise de Pedidos KSB", "📦 Itens Cadastrados", "📋 Histórico de Auditorias"]
elif perfil == "PROCESSISTA":
    opcoes_menu = ["📦 Itens Cadastrados"]
else:
    opcoes_menu = ["📄 Análise de Pedidos KSB"]

menu = st.sidebar.radio("Menu", opcoes_menu)
pode_editar_materiais = perfil in ["ADMIN", "PROCESSISTA"]

if menu == "📄 Análise de Pedidos KSB":
    st.title("📄 Analisador de Pedidos KSB")
    st.write("Sistema de extração e auditoria automática de pedidos.")
    uploaded_files = st.file_uploader("Selecione os PDFs", type=["pdf"], accept_multiple_files=True)

    if uploaded_files:
        st.success(f"{len(uploaded_files)} PDF(s) carregado(s)")
        if st.button("🚀 PROCESSAR PEDIDOS"):
            todos_dados = []
            todas_analises = []
            progress = st.progress(0)
            with st.spinner("Processando PDFs..."):
                for idx, arquivo in enumerate(uploaded_files):
                    with open(arquivo.name, "wb") as f:
                        f.write(arquivo.getbuffer())
                    df_dados, df_analise = processar_pdf(arquivo.name)
                    todos_dados.append(df_dados)
                    todas_analises.append(df_analise)
                    progress.progress(int(((idx + 1) / len(uploaded_files)) * 100))

            df_final = pd.concat(todos_dados, ignore_index=True)
            df_analise_final = pd.concat(todas_analises, ignore_index=True)
            exibir_cards_auditoria(df_analise_final)
            exibir_cards_comercial(df_analise_final)
            nome_avaliacao_pdf = titulo_avaliacao_pedidos(df_analise_final)
            pdf_bytes = gerar_pdf_auditoria(df_analise_final)
            st.download_button(
                "📄 Baixar Avaliação em PDF",
                pdf_bytes,
                f"{nome_avaliacao_pdf}.pdf",
                "application/pdf",
            )
            st.divider()
            st.subheader("📦 Dados Extraídos")
            st.dataframe(df_final, use_container_width=True)
            st.download_button("📥 Download CSV", df_final.to_csv(index=False, sep=";").encode("utf-8-sig"), "pedidos_extraidos.csv", "text/csv")
            excel_path = "pedidos_extraidos.xlsx"
            with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
                df_final.to_excel(writer, index=False, sheet_name="Pedidos")
                df_analise_final.to_excel(writer, index=False, sheet_name="Auditoria")
            with open(excel_path, "rb") as f:
                st.download_button("📥 Download Excel", f, "pedidos_extraidos.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            st.success("Processamento concluído com sucesso!")

elif menu == "📦 Itens Cadastrados":
    st.title("📦 Itens Cadastrados")
    for chave, valor in [("modo_material", None), ("material_em_edicao", None), ("confirmar_exclusao", False), ("mostrar_importacao", False)]:
        if chave not in st.session_state:
            st.session_state[chave] = valor

    df_materiais = pd.DataFrame(
        listar_materiais_completo(),
        columns=["Código Material", "Descrição", "Material", "Norma", "NCM", "Unidade", "Código Interno Jundiaí", "Código Interno Várzea", "Preço Unitário Líquido", "Última Revisão", "Usuário Última Revisão"],
    )

    filtro_material = st.text_input("Pesquisar material", placeholder="Código, descrição ou código interno...")
    if filtro_material and not df_materiais.empty:
        p = filtro_material.strip()
        df_materiais = df_materiais[
            df_materiais["Código Material"].astype(str).str.contains(p, case=False, na=False)
            | df_materiais["Descrição"].astype(str).str.contains(p, case=False, na=False)
            | df_materiais["Código Interno Jundiaí"].astype(str).str.contains(p, case=False, na=False)
            | df_materiais["Código Interno Várzea"].astype(str).str.contains(p, case=False, na=False)
        ]
    elif not filtro_material and len(df_materiais) > 300:
        st.caption("Exibindo os primeiros 300 registros. Use a pesquisa para localizar um material específico.")
        df_materiais = df_materiais.head(300)

    if df_materiais.empty:
        st.info("Nenhum item cadastrado.")
        materiais_selecionados = pd.DataFrame()
    else:
        df_materiais.insert(0, "Selecionar", False)
        tabela_materiais = st.data_editor(df_materiais, use_container_width=True, hide_index=True)
        materiais_selecionados = tabela_materiais[tabela_materiais["Selecionar"] == True]

    st.divider()
    col_importar, col_novo, col_editar, col_excluir = st.columns(4)
    with col_importar:
        if st.button("📥 Importar Excel", disabled=not pode_editar_materiais):
            st.session_state.mostrar_importacao = True
    with col_novo:
        if st.button("➕ Novo Material", disabled=not pode_editar_materiais):
            st.session_state.modo_material = "novo"
            st.session_state.material_em_edicao = None
            st.rerun()
    with col_editar:
        if st.button("✏️ Editar Material", disabled=not pode_editar_materiais):
            if materiais_selecionados.empty:
                st.warning("Selecione um item.")
            elif len(materiais_selecionados) > 1:
                st.warning("Selecione apenas um item.")
            else:
                st.session_state.modo_material = "editar"
                st.session_state.material_em_edicao = materiais_selecionados.iloc[0]
                st.rerun()
    with col_excluir:
        if st.button("🗑 Excluir Selecionados", disabled=not pode_editar_materiais):
            if materiais_selecionados.empty:
                st.warning("Selecione ao menos um item.")
            else:
                st.session_state.confirmar_exclusao = True

    if st.session_state.confirmar_exclusao and not materiais_selecionados.empty:
        st.warning(f"⚠ Deseja excluir {len(materiais_selecionados)} item(ns)?")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("✅ Confirmar Exclusão"):
                for _, linha in materiais_selecionados.iterrows():
                    excluir_material(linha["Código Material"])
                st.session_state.confirmar_exclusao = False
                st.success("Itens excluídos com sucesso!")
                st.rerun()
        with c2:
            if st.button("❌ Cancelar Exclusão"):
                st.session_state.confirmar_exclusao = False
                st.rerun()

    if st.session_state.mostrar_importacao:
        st.divider()
        st.subheader("📥 Importação de Materiais")
        arquivo_excel = st.file_uploader("Selecione o arquivo Excel", type=["xlsx"], key="upload_excel")
        if arquivo_excel is not None:
            try:
                df_importacao, relatorio_abas = preparar_planilha_materiais(arquivo_excel)
                for item in relatorio_abas:
                    st.caption(item)
                if df_importacao.empty:
                    st.warning("Nenhuma linha válida foi encontrada para importação.")
                else:
                    st.success(f"Arquivo lido com {len(df_importacao)} material(is) válido(s).")
                    st.dataframe(df_importacao.head(20), use_container_width=True)
                    st.caption("Pré-visualização limitada a 20 linhas para evitar estouro de memória no Render Free.")
                    if st.button("🚀 Importar Materiais"):
                        inseridos = 0
                        atualizados = 0
                        data_auto = date.today().isoformat()
                        barra = st.progress(0)
                        total = len(df_importacao)
                        for idx, linha in df_importacao.iterrows():
                            codigo = limpar_texto(linha["Código Material"])
                            args = (
                                codigo,
                                limpar_texto(linha["Descrição"]),
                                limpar_texto(linha["Material"]),
                                limpar_texto(linha["Norma"]),
                                limpar_texto(linha["NCM"]),
                                limpar_texto(linha["Unidade"]),
                                limpar_texto(linha["Código Interno Jundiaí"]),
                                limpar_texto(linha["Código Interno Várzea"]),
                                moeda_para_float_importacao(linha["Preço Unitário Líquido"]),
                                data_auto,
                                usuario_revisao_atual,
                            )
                            if buscar_material(codigo):
                                atualizar_material(*args)
                                atualizados += 1
                            else:
                                inserir_material(*args)
                                inseridos += 1
                            if total:
                                barra.progress(min(int(((idx + 1) / total) * 100), 100))
                        st.success(f"Importação concluída! {inseridos} inseridos e {atualizados} atualizados.")
                        st.session_state.mostrar_importacao = False
                        st.rerun()
            except Exception as erro:
                st.error(f"Erro ao importar Excel: {erro}")

    if st.session_state.modo_material is not None:
        st.divider()
        m = st.session_state.material_em_edicao
        st.subheader("➕ Novo Material" if st.session_state.modo_material == "novo" else "✏️ Editar Material")
        codigo = st.text_input("Código Material KSB", value="" if m is None else m["Código Material"], disabled=st.session_state.modo_material == "editar")
        descricao = st.text_input("Descrição", value="" if m is None else m["Descrição"])
        material = st.text_input("Material", value="" if m is None else m["Material"])
        norma = st.text_input("Norma", value="" if m is None else m["Norma"])
        ncm = st.text_input("NCM", value="" if m is None else m["NCM"])
        unidade = st.text_input("Unidade Medida", value="" if m is None else m["Unidade"])
        jundiai = st.text_input("Código Interno Jundiaí", value="" if m is None else m["Código Interno Jundiaí"])
        varzea = st.text_input("Código Interno Várzea", value="" if m is None else m["Código Interno Várzea"])
        preco = st.number_input("Preço Unitário Líquido", value=0.0 if m is None else float(m["Preço Unitário Líquido"]), format="%.2f")
        data_auto = date.today().isoformat()
        st.text_input("Data Última Revisão", value=data_auto, disabled=True)
        st.text_input("Usuário Última Revisão", value=str(usuario_revisao_atual), disabled=True)
        c1, c2 = st.columns(2)
        with c1:
            if st.button("💾 Salvar"):
                args = (codigo, descricao, material, norma, ncm, unidade, jundiai, varzea, preco, data_auto, usuario_revisao_atual)
                if st.session_state.modo_material == "novo":
                    inserir_material(*args)
                    st.success("Material cadastrado com sucesso!")
                else:
                    atualizar_material(*args)
                    st.success("Material atualizado com sucesso!")
                st.session_state.modo_material = None
                st.session_state.material_em_edicao = None
                st.rerun()
        with c2:
            if st.button("❌ Cancelar"):
                st.session_state.modo_material = None
                st.session_state.material_em_edicao = None
                st.rerun()

elif menu == "🏛 Regras Fiscais":
    st.title("🏛 Regras Fiscais")
    for chave, valor in [("modo_regra", None), ("regra_em_edicao", None), ("confirmar_exclusao_regra", False)]:
        if chave not in st.session_state:
            st.session_state[chave] = valor
    df_regras = pd.DataFrame(listar_regras_fiscais(), columns=["ID", "NCM", "ICMS", "IPI", "Observação", "Ativo"])
    filtro_regra = st.text_input("Pesquisar regra", placeholder="NCM", key="filtro_regra")
    if filtro_regra and not df_regras.empty:
        df_regras = df_regras[df_regras["NCM"].astype(str).str.contains(filtro_regra.strip(), case=False, na=False)]
    if df_regras.empty:
        st.info("Nenhuma regra fiscal cadastrada.")
        regras_selecionadas = pd.DataFrame()
    else:
        df_regras.insert(0, "Selecionar", False)
        tabela_regras = st.data_editor(df_regras, use_container_width=True, hide_index=True)
        regras_selecionadas = tabela_regras[tabela_regras["Selecionar"] == True]
    st.divider()
    col_nova, col_editar, col_excluir = st.columns(3)
    with col_nova:
        if st.button("➕ Nova Regra", key="btn_nova_regra"):
            st.session_state.modo_regra = "novo"
            st.session_state.regra_em_edicao = None
            st.rerun()
    with col_editar:
        if st.button("✏️ Editar Regra", key="btn_editar_regra"):
            if len(regras_selecionadas) != 1:
                st.warning("Selecione apenas uma regra.")
            else:
                st.session_state.modo_regra = "editar"
                st.session_state.regra_em_edicao = regras_selecionadas.iloc[0]
                st.rerun()
    with col_excluir:
        if st.button("🗑 Excluir Regra", key="btn_excluir_regra"):
            if regras_selecionadas.empty:
                st.warning("Selecione ao menos uma regra.")
            else:
                st.session_state.confirmar_exclusao_regra = True
    if st.session_state.confirmar_exclusao_regra and not regras_selecionadas.empty:
        st.warning(f"⚠ Deseja excluir {len(regras_selecionadas)} regra(s)?")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("✅ Confirmar Exclusão", key="confirmar_delete_regra"):
                for _, linha in regras_selecionadas.iterrows():
                    excluir_regra_fiscal(int(linha["ID"]))
                st.session_state.confirmar_exclusao_regra = False
                st.success("Regras excluídas com sucesso!")
                st.rerun()
        with c2:
            if st.button("❌ Cancelar Exclusão", key="cancelar_delete_regra"):
                st.session_state.confirmar_exclusao_regra = False
                st.rerun()
    if st.session_state.modo_regra is not None:
        regra = st.session_state.regra_em_edicao
        st.divider()
        st.subheader("➕ Nova Regra Fiscal" if st.session_state.modo_regra == "novo" else "✏️ Editar Regra Fiscal")
        ncm = st.text_input("NCM", value="" if regra is None else str(regra["NCM"]), key="rf_ncm")
        icms = st.number_input("ICMS (%)", value=18.0 if regra is None else float(regra["ICMS"]), key="rf_icms")
        ipi = st.number_input("IPI (%)", value=5.0 if regra is None else float(regra["IPI"]), key="rf_ipi")
        observacao = st.text_area("Observação", value="" if regra is None else str(regra["Observação"]), key="rf_obs")
        ativo = 1
        c1, c2 = st.columns(2)
        with c1:
            if st.button("💾 Salvar Regra", key="btn_salvar_regra"):
                if st.session_state.modo_regra == "novo":
                    inserir_regra_fiscal(ncm, icms, ipi, observacao, ativo)
                else:
                    atualizar_regra_fiscal(int(regra["ID"]), ncm, icms, ipi, observacao, ativo)
                st.success("Regra fiscal salva.")
                st.session_state.modo_regra = None
                st.session_state.regra_em_edicao = None
                st.rerun()
        with c2:
            if st.button("❌ Cancelar", key="btn_cancelar_regra"):
                st.session_state.modo_regra = None
                st.session_state.regra_em_edicao = None
                st.rerun()

elif menu == "👤 Usuários":
    st.title("👤 Usuários")
    if perfil != "ADMIN":
        st.error("Acesso negado.")
        st.stop()
    def atualizar_usuario(id_usuario, nome, usuario, perfil_usuario, ativo):
        conn = conectar(); cursor = conn.cursor()
        try:
            cursor.execute("UPDATE usuarios SET nome=%s, usuario=%s, perfil=%s, ativo=%s WHERE id=%s", (nome, usuario, perfil_usuario, ativo, id_usuario)); conn.commit()
        except Exception:
            conn.rollback(); raise
        finally:
            cursor.close(); conn.close()
    def alterar_status_usuario(id_usuario, ativo):
        conn = conectar(); cursor = conn.cursor()
        try:
            cursor.execute("UPDATE usuarios SET ativo=%s WHERE id=%s", (ativo, id_usuario)); conn.commit()
        finally:
            cursor.close(); conn.close()
    def alterar_senha_usuario(id_usuario, nova_senha):
        conn = conectar(); cursor = conn.cursor()
        try:
            cursor.execute("UPDATE usuarios SET senha=%s WHERE id=%s", (nova_senha, id_usuario)); conn.commit()
        finally:
            cursor.close(); conn.close()
    for chave in ["modo_usuario", "usuario_em_edicao"]:
        if chave not in st.session_state:
            st.session_state[chave] = None
    df_usuarios = pd.DataFrame(listar_usuarios(), columns=["ID", "Nome", "Usuário", "Perfil", "Ativo"])
    if not df_usuarios.empty:
        df_usuarios["Status"] = df_usuarios["Ativo"].apply(lambda x: "Ativo" if int(x) == 1 else "Bloqueado")
        df_usuarios = df_usuarios[["ID", "Nome", "Usuário", "Perfil", "Status", "Ativo"]]
    filtro = st.text_input("Pesquisar usuário", placeholder="Nome, usuário ou perfil", key="filtro_usuario")
    if filtro and not df_usuarios.empty:
        p = filtro.strip()
        df_usuarios = df_usuarios[df_usuarios["Nome"].astype(str).str.contains(p, case=False, na=False) | df_usuarios["Usuário"].astype(str).str.contains(p, case=False, na=False) | df_usuarios["Perfil"].astype(str).str.contains(p, case=False, na=False)]
    if df_usuarios.empty:
        st.info("Nenhum usuário cadastrado."); usuarios_selecionados = pd.DataFrame()
    else:
        df_usuarios.insert(0, "Selecionar", False)
        tabela_usuarios = st.data_editor(df_usuarios, use_container_width=True, hide_index=True, disabled=["ID", "Nome", "Usuário", "Perfil", "Status", "Ativo"])
        usuarios_selecionados = tabela_usuarios[tabela_usuarios["Selecionar"] == True]
    st.divider(); c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        if st.button("➕ Novo Usuário"):
            st.session_state.modo_usuario = "novo"; st.session_state.usuario_em_edicao = None; st.rerun()
    with c2:
        if st.button("✏️ Editar Usuário"):
            if len(usuarios_selecionados) != 1: st.warning("Selecione apenas um usuário.")
            else: st.session_state.modo_usuario = "editar"; st.session_state.usuario_em_edicao = usuarios_selecionados.iloc[0]; st.rerun()
    with c3:
        if st.button("🔒 Bloquear/Ativar"):
            if len(usuarios_selecionados) != 1: st.warning("Selecione apenas um usuário.")
            else:
                u = usuarios_selecionados.iloc[0]
                if str(u["Usuário"]) == str(st.session_state.usuario_logado): st.warning("Você não pode bloquear o próprio usuário logado.")
                else: alterar_status_usuario(int(u["ID"]), 0 if int(u["Ativo"]) == 1 else 1); st.rerun()
    with c4:
        if st.button("🔑 Redefinir Senha"):
            if len(usuarios_selecionados) != 1: st.warning("Selecione apenas um usuário.")
            else: st.session_state.modo_usuario = "senha"; st.session_state.usuario_em_edicao = usuarios_selecionados.iloc[0]; st.rerun()
    with c5:
        if st.button("🗑️ Excluir Usuário"):
            if len(usuarios_selecionados) != 1: st.warning("Selecione apenas um usuário.")
            else:
                u = usuarios_selecionados.iloc[0]
                if str(u["Usuário"]) == str(st.session_state.usuario_logado): st.warning("Você não pode excluir o próprio usuário logado.")
                else: st.session_state.modo_usuario = "excluir"; st.session_state.usuario_em_edicao = u; st.rerun()
    modo = st.session_state.modo_usuario; u = st.session_state.usuario_em_edicao
    if modo in ["novo", "editar"]:
        st.divider(); st.subheader("➕ Novo Usuário" if modo == "novo" else "✏️ Editar Usuário")
        with st.form("form_usuario"):
            nome = st.text_input("Nome", value="" if u is None else str(u["Nome"])); usuario = st.text_input("Usuário", value="" if u is None else str(u["Usuário"])); senha = st.text_input("Senha", type="password") if modo == "novo" else ""
            perfis = ["ADMIN", "VENDEDORA", "PROCESSISTA"]; perfil_idx = 0 if u is None or str(u["Perfil"]) not in perfis else perfis.index(str(u["Perfil"])); perfil_novo = st.selectbox("Perfil", perfis, index=perfil_idx)
            status = st.selectbox("Status", ["Ativo", "Bloqueado"], index=0 if u is None or int(u["Ativo"]) == 1 else 1)
            salvar = st.form_submit_button("💾 Salvar"); cancelar = st.form_submit_button("❌ Cancelar")
            if salvar:
                if not nome or not usuario or (modo == "novo" and not senha): st.warning("Preencha os campos obrigatórios.")
                else:
                    ativo = 1 if status == "Ativo" else 0
                    if modo == "novo":
                        inserir_usuario(nome, usuario, senha, perfil_novo)
                        for reg in listar_usuarios():
                            if str(reg[2]) == str(usuario): alterar_status_usuario(int(reg[0]), ativo); break
                    else:
                        atualizar_usuario(int(u["ID"]), nome, usuario, perfil_novo, ativo)
                    st.session_state.modo_usuario = None; st.session_state.usuario_em_edicao = None; st.rerun()
            if cancelar: st.session_state.modo_usuario = None; st.session_state.usuario_em_edicao = None; st.rerun()
    elif modo == "senha":
        st.divider(); st.subheader("🔑 Redefinir Senha")
        with st.form("form_senha"):
            nova = st.text_input("Nova senha", type="password"); confirma = st.text_input("Confirmar nova senha", type="password"); salvar = st.form_submit_button("💾 Salvar nova senha"); cancelar = st.form_submit_button("❌ Cancelar")
            if salvar:
                if not nova or nova != confirma: st.warning("As senhas não conferem.")
                else: alterar_senha_usuario(int(u["ID"]), nova); st.session_state.modo_usuario = None; st.session_state.usuario_em_edicao = None; st.rerun()
            if cancelar: st.session_state.modo_usuario = None; st.session_state.usuario_em_edicao = None; st.rerun()
    elif modo == "excluir":
        st.divider(); st.warning(f"Confirma excluir o usuário {u['Usuário']}?"); c1, c2 = st.columns(2)
        with c1:
            if st.button("✅ Confirmar Exclusão"): excluir_usuario(int(u["ID"])); st.session_state.modo_usuario = None; st.session_state.usuario_em_edicao = None; st.rerun()
        with c2:
            if st.button("❌ Cancelar Exclusão"): st.session_state.modo_usuario = None; st.session_state.usuario_em_edicao = None; st.rerun()

elif menu == "🛠️ Ferramentas Administrativas":
    st.title("🛠️ Ferramentas Administrativas")
    if perfil != "ADMIN": st.error("Acesso negado."); st.stop()
    st.warning("Área restrita. Use apenas para manutenção do sistema.")
    with st.expander("🗄️ Migração SQLite → PostgreSQL/Neon", expanded=False):
        st.write("Origem: database.db"); st.write("Destino: banco PostgreSQL configurado nas variáveis de ambiente")
        limpar_destino = st.checkbox("Limpar dados atuais do PostgreSQL antes de migrar", value=False); confirmacao = st.text_input("Digite MIGRAR para liberar o botão", value="")
        if confirmacao == "MIGRAR" and st.button("🚀 Executar Migração"):
            try:
                from migrar_sqlite_para_postgres import migrar
                with st.spinner("Migrando dados..."):
                    totais = migrar(sqlite_path="database.db", limpar=limpar_destino)
                st.success("Migração concluída com sucesso.")
                for tabela, total in totais.items(): st.write(f"{tabela}: {total} registro(s) migrado(s)")
            except Exception as erro:
                st.error("Erro ao executar migração."); st.exception(erro)

elif menu == "📋 Histórico de Auditorias":
    st.title("📋 Histórico de Auditorias")
    st.info("Módulo em desenvolvimento")
