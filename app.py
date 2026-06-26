from datetime import date

import pandas as pd
import streamlit as st

from database import (
    atualizar_material,
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
    atualizar_regra_fiscal,
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

# ====================================
# LOGIN
# ====================================

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
    opcoes_menu = [
        "📄 Análise de Pedidos KSB",
        "📦 Itens Cadastrados",
        "🏛 Regras Fiscais",
        "📋 Histórico de Auditorias",
        "👤 Usuários",
        "🛠️ Ferramentas Administrativas",
    ]
elif perfil == "VENDEDORA":
    opcoes_menu = ["📄 Análise de Pedidos KSB", "📦 Itens Cadastrados", "📋 Histórico de Auditorias"]
elif perfil == "PROCESSISTA":
    opcoes_menu = ["📦 Itens Cadastrados"]
else:
    opcoes_menu = ["📄 Análise de Pedidos KSB"]

menu = st.sidebar.radio("Menu", opcoes_menu)
pode_editar_materiais = perfil in ["ADMIN", "PROCESSISTA"]

# ====================================
# ANÁLISE
# ====================================

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

            total_itens = len(df_analise_final)
            total_ok = len(df_analise_final[df_analise_final["Status"] == "OK"])
            total_div = len(df_analise_final[df_analise_final["Status"] == "DIVERGENTE"])

            col1, col2, col3 = st.columns(3)
            col1.metric("Itens Processados", total_itens)
            col2.metric("Itens OK", total_ok)
            col3.metric("Itens Divergentes", total_div)

            st.divider()
            st.subheader("📋 Auditoria")

            if "Divergencias" in df_analise_final.columns:
                df_analise_final["Divergencias"] = df_analise_final["Divergencias"].astype(str).str.replace("|", "\n")

            st.dataframe(df_analise_final, use_container_width=True, height=400)

            st.divider()
            st.subheader("📦 Dados Extraídos")
            st.dataframe(df_final, use_container_width=True)

            csv = df_final.to_csv(index=False, sep=";").encode("utf-8-sig")
            st.download_button("📥 Download CSV", csv, "pedidos_extraidos.csv", "text/csv")

            excel_path = "pedidos_extraidos.xlsx"
            with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
                df_final.to_excel(writer, index=False, sheet_name="Pedidos")
                df_analise_final.to_excel(writer, index=False, sheet_name="Auditoria")

            with open(excel_path, "rb") as f:
                st.download_button(
                    "📥 Download Excel",
                    f,
                    "pedidos_extraidos.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

            st.success("Processamento concluído com sucesso!")

# ====================================
# MATERIAIS
# ====================================

elif menu == "📦 Itens Cadastrados":
    st.title("📦 Itens Cadastrados")

    if "modo_material" not in st.session_state:
        st.session_state.modo_material = None
    if "material_em_edicao" not in st.session_state:
        st.session_state.material_em_edicao = None
    if "confirmar_exclusao" not in st.session_state:
        st.session_state.confirmar_exclusao = False
    if "mostrar_importacao" not in st.session_state:
        st.session_state.mostrar_importacao = False

    lista_materiais = listar_materiais_completo()
    df_materiais = pd.DataFrame(
        lista_materiais,
        columns=[
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
        ],
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
                df_importacao = pd.read_excel(arquivo_excel)
                st.dataframe(df_importacao, use_container_width=True)
                if st.button("🚀 Importar Materiais"):
                    inseridos = 0
                    atualizados = 0
                    data_auto = date.today().isoformat()
                    preco_coluna = "Preço Unitário Líquido" if "Preço Unitário Líquido" in df_importacao.columns else "Preço Revisado"
                    for _, linha in df_importacao.iterrows():
                        codigo = str(linha["Código Material"])
                        args = (
                            codigo,
                            str(linha["Descrição"]),
                            str(linha["Material"]),
                            str(linha["Norma"]),
                            str(linha["NCM"]),
                            str(linha["Unidade"]),
                            str(linha["Código Interno Jundiaí"]),
                            str(linha["Código Interno Várzea"]),
                            float(linha[preco_coluna]),
                            data_auto,
                            usuario_revisao_atual,
                        )
                        if buscar_material(codigo):
                            atualizar_material(*args)
                            atualizados += 1
                        else:
                            inserir_material(*args)
                            inseridos += 1
                    st.success(f"Importação concluída! {inseridos} inseridos e {atualizados} atualizados.")
                    st.session_state.mostrar_importacao = False
                    st.rerun()
            except Exception as erro:
                st.error(f"Erro ao ler Excel: {erro}")

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

# ====================================
# REGRAS FISCAIS - SOMENTE NCM
# ====================================

elif menu == "🏛 Regras Fiscais":
    st.title("🏛 Regras Fiscais")

    if "modo_regra" not in st.session_state:
        st.session_state.modo_regra = None
    if "regra_em_edicao" not in st.session_state:
        st.session_state.regra_em_edicao = None
    if "confirmar_exclusao_regra" not in st.session_state:
        st.session_state.confirmar_exclusao_regra = False

    lista_regras = listar_regras_fiscais()
    df_regras = pd.DataFrame(lista_regras, columns=["ID", "NCM", "ICMS", "IPI", "Observação", "Ativo"])

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
            if regras_selecionadas.empty:
                st.warning("Selecione uma regra.")
            elif len(regras_selecionadas) > 1:
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

# ====================================
# USUÁRIOS
# ====================================

elif menu == "👤 Usuários":
    st.title("👤 Usuários")
    if perfil != "ADMIN":
        st.error("Acesso negado.")
        st.stop()

    def atualizar_usuario(id_usuario, nome, usuario, perfil_usuario, ativo):
        conn = conectar()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE usuarios SET nome=%s, usuario=%s, perfil=%s, ativo=%s WHERE id=%s",
                (nome, usuario, perfil_usuario, ativo, id_usuario),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    def alterar_status_usuario(id_usuario, ativo):
        conn = conectar()
        cursor = conn.cursor()
        try:
            cursor.execute("UPDATE usuarios SET ativo=%s WHERE id=%s", (ativo, id_usuario))
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    def alterar_senha_usuario(id_usuario, nova_senha):
        conn = conectar()
        cursor = conn.cursor()
        try:
            cursor.execute("UPDATE usuarios SET senha=%s WHERE id=%s", (nova_senha, id_usuario))
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    if "modo_usuario" not in st.session_state:
        st.session_state.modo_usuario = None
    if "usuario_em_edicao" not in st.session_state:
        st.session_state.usuario_em_edicao = None

    df_usuarios = pd.DataFrame(listar_usuarios(), columns=["ID", "Nome", "Usuário", "Perfil", "Ativo"])
    if not df_usuarios.empty:
        df_usuarios["Status"] = df_usuarios["Ativo"].apply(lambda x: "Ativo" if int(x) == 1 else "Bloqueado")
        df_usuarios = df_usuarios[["ID", "Nome", "Usuário", "Perfil", "Status", "Ativo"]]

    filtro = st.text_input("Pesquisar usuário", placeholder="Nome, usuário ou perfil", key="filtro_usuario")
    if filtro and not df_usuarios.empty:
        p = filtro.strip()
        df_usuarios = df_usuarios[
            df_usuarios["Nome"].astype(str).str.contains(p, case=False, na=False)
            | df_usuarios["Usuário"].astype(str).str.contains(p, case=False, na=False)
            | df_usuarios["Perfil"].astype(str).str.contains(p, case=False, na=False)
        ]

    if df_usuarios.empty:
        st.info("Nenhum usuário cadastrado.")
        usuarios_selecionados = pd.DataFrame()
    else:
        df_usuarios.insert(0, "Selecionar", False)
        tabela_usuarios = st.data_editor(df_usuarios, use_container_width=True, hide_index=True, disabled=["ID", "Nome", "Usuário", "Perfil", "Status", "Ativo"])
        usuarios_selecionados = tabela_usuarios[tabela_usuarios["Selecionar"] == True]

    st.divider()
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        if st.button("➕ Novo Usuário"):
            st.session_state.modo_usuario = "novo"
            st.session_state.usuario_em_edicao = None
            st.rerun()
    with c2:
        if st.button("✏️ Editar Usuário"):
            if len(usuarios_selecionados) != 1:
                st.warning("Selecione apenas um usuário.")
            else:
                st.session_state.modo_usuario = "editar"
                st.session_state.usuario_em_edicao = usuarios_selecionados.iloc[0]
                st.rerun()
    with c3:
        if st.button("🔒 Bloquear/Ativar"):
            if len(usuarios_selecionados) != 1:
                st.warning("Selecione apenas um usuário.")
            else:
                u = usuarios_selecionados.iloc[0]
                if str(u["Usuário"]) == str(st.session_state.usuario_logado):
                    st.warning("Você não pode bloquear o próprio usuário logado.")
                else:
                    alterar_status_usuario(int(u["ID"]), 0 if int(u["Ativo"]) == 1 else 1)
                    st.rerun()
    with c4:
        if st.button("🔑 Redefinir Senha"):
            if len(usuarios_selecionados) != 1:
                st.warning("Selecione apenas um usuário.")
            else:
                st.session_state.modo_usuario = "senha"
                st.session_state.usuario_em_edicao = usuarios_selecionados.iloc[0]
                st.rerun()
    with c5:
        if st.button("🗑️ Excluir Usuário"):
            if len(usuarios_selecionados) != 1:
                st.warning("Selecione apenas um usuário.")
            else:
                u = usuarios_selecionados.iloc[0]
                if str(u["Usuário"]) == str(st.session_state.usuario_logado):
                    st.warning("Você não pode excluir o próprio usuário logado.")
                else:
                    st.session_state.modo_usuario = "excluir"
                    st.session_state.usuario_em_edicao = u
                    st.rerun()

    modo = st.session_state.modo_usuario
    u = st.session_state.usuario_em_edicao

    if modo in ["novo", "editar"]:
        st.divider()
        st.subheader("➕ Novo Usuário" if modo == "novo" else "✏️ Editar Usuário")
        with st.form("form_usuario"):
            nome = st.text_input("Nome", value="" if u is None else str(u["Nome"]))
            usuario = st.text_input("Usuário", value="" if u is None else str(u["Usuário"]))
            senha = st.text_input("Senha", type="password") if modo == "novo" else ""
            perfis = ["ADMIN", "VENDEDORA", "PROCESSISTA"]
            perfil_idx = 0 if u is None or str(u["Perfil"]) not in perfis else perfis.index(str(u["Perfil"]))
            perfil_novo = st.selectbox("Perfil", perfis, index=perfil_idx)
            status = st.selectbox("Status", ["Ativo", "Bloqueado"], index=0 if u is None or int(u["Ativo"]) == 1 else 1)
            salvar = st.form_submit_button("💾 Salvar")
            cancelar = st.form_submit_button("❌ Cancelar")

            if salvar:
                if not nome or not usuario or (modo == "novo" and not senha):
                    st.warning("Preencha os campos obrigatórios.")
                else:
                    ativo = 1 if status == "Ativo" else 0
                    if modo == "novo":
                        inserir_usuario(nome, usuario, senha, perfil_novo)
                        for reg in listar_usuarios():
                            if str(reg[2]) == str(usuario):
                                alterar_status_usuario(int(reg[0]), ativo)
                                break
                    else:
                        atualizar_usuario(int(u["ID"]), nome, usuario, perfil_novo, ativo)
                    st.session_state.modo_usuario = None
                    st.session_state.usuario_em_edicao = None
                    st.rerun()
            if cancelar:
                st.session_state.modo_usuario = None
                st.session_state.usuario_em_edicao = None
                st.rerun()

    elif modo == "senha":
        st.divider()
        st.subheader("🔑 Redefinir Senha")
        with st.form("form_senha"):
            nova = st.text_input("Nova senha", type="password")
            confirma = st.text_input("Confirmar nova senha", type="password")
            salvar = st.form_submit_button("💾 Salvar nova senha")
            cancelar = st.form_submit_button("❌ Cancelar")
            if salvar:
                if not nova or nova != confirma:
                    st.warning("As senhas não conferem.")
                else:
                    alterar_senha_usuario(int(u["ID"]), nova)
                    st.session_state.modo_usuario = None
                    st.session_state.usuario_em_edicao = None
                    st.rerun()
            if cancelar:
                st.session_state.modo_usuario = None
                st.session_state.usuario_em_edicao = None
                st.rerun()

    elif modo == "excluir":
        st.divider()
        st.warning(f"Confirma excluir o usuário {u['Usuário']}?")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("✅ Confirmar Exclusão"):
                excluir_usuario(int(u["ID"]))
                st.session_state.modo_usuario = None
                st.session_state.usuario_em_edicao = None
                st.rerun()
        with c2:
            if st.button("❌ Cancelar Exclusão"):
                st.session_state.modo_usuario = None
                st.session_state.usuario_em_edicao = None
                st.rerun()

elif menu == "🛠️ Ferramentas Administrativas":
    st.title("🛠️ Ferramentas Administrativas")
    if perfil != "ADMIN":
        st.error("Acesso negado.")
        st.stop()
    st.warning("Área restrita. Use apenas para manutenção do sistema.")
    with st.expander("🗄️ Migração SQLite → PostgreSQL/Neon", expanded=False):
        st.write("Origem: database.db")
        st.write("Destino: banco PostgreSQL configurado nas variáveis de ambiente")
        limpar_destino = st.checkbox("Limpar dados atuais do PostgreSQL antes de migrar", value=False)
        confirmacao = st.text_input("Digite MIGRAR para liberar o botão", value="")
        if confirmacao == "MIGRAR" and st.button("🚀 Executar Migração"):
            try:
                from migrar_sqlite_para_postgres import migrar

                with st.spinner("Migrando dados..."):
                    totais = migrar(sqlite_path="database.db", limpar=limpar_destino)
                st.success("Migração concluída com sucesso.")
                for tabela, total in totais.items():
                    st.write(f"{tabela}: {total} registro(s) migrado(s)")
            except Exception as erro:
                st.error("Erro ao executar migração.")
                st.exception(erro)

elif menu == "📋 Histórico de Auditorias":
    st.title("📋 Histórico de Auditorias")
    st.info("Módulo em desenvolvimento")
