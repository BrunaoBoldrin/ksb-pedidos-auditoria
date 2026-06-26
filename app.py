from database import (
    listar_materiais,
    listar_materiais_completo,
    inserir_material,
    atualizar_material,
    excluir_material,
    buscar_material,
    listar_regras_fiscais,
    inserir_regra_fiscal,
    atualizar_regra_fiscal,
    excluir_regra_fiscal,
    buscar_regra_fiscal,
    localizar_regra_fiscal,
    conectar,
    buscar_usuario_login,
    listar_usuarios,
    inserir_usuario,
    excluir_usuario

)

import streamlit as st
import pandas as pd
from datetime import date

from database import localizar_regra_fiscal
from parser import processar_pdf

# ====================================
# CONFIG PAGINA
# ====================================

st.set_page_config(
    page_title="Analisador de Pedidos",
    page_icon="📄",
    layout="wide"
)


# ====================================
# LOGIN
# ====================================

if "usuario_logado" not in st.session_state:
    st.session_state.usuario_logado = None

if "nome_usuario" not in st.session_state:
    st.session_state.nome_usuario = None

if "perfil_usuario" not in st.session_state:
    st.session_state.perfil_usuario = None


# ====================================
# CSS
# ====================================

st.markdown(
    """
<style>

.main {
    padding-top: 20px;
}

.stButton button {
    width: 100%;
    height: 50px;
    font-size: 18px;
    font-weight: bold;
}

.status-ok {
    color: green;
    font-weight: bold;
}

.status-div {
    color: red;
    font-weight: bold;
}

</style>
""",
    unsafe_allow_html=True,
)


# ====================================
# LOGIN
# ====================================

if st.session_state.usuario_logado is None:

    st.title("🔐 Login")

    usuario = st.text_input(
        "Usuário"
    )

    senha = st.text_input(
        "Senha",
        type="password"
    )

    if st.button("Entrar"):

        resultado = buscar_usuario_login(
            usuario,
            senha
        )

        if resultado:

            st.session_state.usuario_logado = resultado[2]
            st.session_state.nome_usuario = resultado[1]
            st.session_state.perfil_usuario = resultado[3]
            st.rerun()

        else:

            st.error(
                "Usuário ou senha inválidos"
            )

    st.stop()


# ====================================
# MENU
# ====================================

with st.sidebar:

    st.success(
        f"👤 {st.session_state.nome_usuario}"
    )

    st.caption(
        f"Perfil: {st.session_state.perfil_usuario}"
    )

    if st.button("🚪 Logout"):

        st.session_state.usuario_logado = None
        st.session_state.nome_usuario = None
        st.session_state.perfil_usuario = None

        st.rerun()

perfil = st.session_state.perfil_usuario
usuario_revisao_atual = st.session_state.nome_usuario or st.session_state.usuario_logado

if perfil == "ADMIN":

    opcoes_menu = [
        "📄 Análise de Pedidos KSB",
        "📦 Itens Cadastrados",
        "🏛 Regras Fiscais",
        "📋 Histórico de Auditorias",
        "👤 Usuários",
        "🛠️ Ferramentas Administrativas"
    ]

elif perfil == "VENDEDORA":

    opcoes_menu = [
        "📄 Análise de Pedidos KSB",
        "📦 Itens Cadastrados",
        "📋 Histórico de Auditorias"
    ]

elif perfil == "PROCESSISTA":

    opcoes_menu = [
        "📦 Itens Cadastrados"
    ]

else:

    opcoes_menu = [
        "📄 Análise de Pedidos KSB"
    ]

menu = st.sidebar.radio(
    "Menu",
    opcoes_menu
)

pode_editar_materiais = perfil in ["ADMIN", "PROCESSISTA"]


# ====================================
# ANALISE DE PEDIDOS
# ====================================

if menu == "📄 Análise de Pedidos KSB":

    st.title("📄 Analisador de Pedidos KSB")

    st.write(
        "Sistema de extração e auditoria automática de pedidos."
    )

    uploaded_files = st.file_uploader(
        "Selecione os PDFs",
        type=["pdf"],
        accept_multiple_files=True
    )

    if uploaded_files:

        st.success(
            f"{len(uploaded_files)} PDF(s) carregado(s)"
        )

        if st.button("🚀 PROCESSAR PEDIDOS"):

            todos_dados = []
            todas_analises = []

            progress = st.progress(0)

            with st.spinner("Processando PDFs..."):

                for idx, arquivo in enumerate(uploaded_files):

                    with open(
                        arquivo.name,
                        "wb"
                    ) as f:

                        f.write(
                            arquivo.getbuffer()
                        )

                    df_dados, df_analise = processar_pdf(
                        arquivo.name
                    )

                    todos_dados.append(df_dados)
                    todas_analises.append(df_analise)

                    progresso = int(((idx + 1) / len(uploaded_files)) * 100)
                    progress.progress(progresso)

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

            def colorir_status(val):
                if val == "OK":
                    return "background-color: #b6ffb6"
                if val == "DIVERGENTE":
                    return "background-color: #ffb6b6"
                return ""

            df_analise_final["Divergencias"] = (
                df_analise_final["Divergencias"].astype(str).str.replace("|", "\n")
            )

            st.data_editor(
                df_analise_final.style.map(colorir_status, subset=["Status"]),
                use_container_width=True,
                height=400
            )

            st.divider()
            st.subheader("📦 Dados Extraídos")

            st.dataframe(df_final, use_container_width=True)

            csv = df_final.to_csv(index=False, sep=";").encode("utf-8-sig")

            st.download_button(
                label="📥 Download CSV",
                data=csv,
                file_name="pedidos_extraidos.csv",
                mime="text/csv"
            )

            excel_path = "pedidos_extraidos.xlsx"

            with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
                df_final.to_excel(writer, index=False, sheet_name="Pedidos")
                df_analise_final.to_excel(writer, index=False, sheet_name="Auditoria")

            with open(excel_path, "rb") as f:
                st.download_button(
                    label="📥 Download Excel",
                    data=f,
                    file_name="pedidos_extraidos.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

            st.success("Processamento concluído com sucesso!")

# ====================================
# ITENS CADASTRADOS
# ====================================

elif menu == "📦 Itens Cadastrados":

    st.title("📦 Itens Cadastrados")

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
            "Usuário Última Revisão"
        ]
    )

    filtro_material = st.text_input(
        "Pesquisar material",
        placeholder="Código, descrição ou código interno..."
    )

    if filtro_material:
        pesquisa = filtro_material.strip()
        df_materiais = df_materiais[
            df_materiais["Código Material"].astype(str).str.contains(pesquisa, case=False, na=False)
            | df_materiais["Descrição"].astype(str).str.contains(pesquisa, case=False, na=False)
            | df_materiais["Código Interno Jundiaí"].astype(str).str.contains(pesquisa, case=False, na=False)
            | df_materiais["Código Interno Várzea"].astype(str).str.contains(pesquisa, case=False, na=False)
        ]

    st.subheader("Itens Cadastrados")

    if df_materiais.empty:
        st.info("Nenhum item cadastrado.")
        materiais_selecionados = pd.DataFrame()
        st.session_state.confirmar_exclusao = False
    else:
        df_materiais.insert(0, "Selecionar", False)
        tabela_materiais = st.data_editor(
            df_materiais,
            use_container_width=True,
            hide_index=True
        )
        materiais_selecionados = tabela_materiais[tabela_materiais["Selecionar"] == True]

    if "modo_material" not in st.session_state:
        st.session_state.modo_material = None

    if "confirmar_exclusao" not in st.session_state:
        st.session_state.confirmar_exclusao = False

    if "mostrar_importacao" not in st.session_state:
        st.session_state.mostrar_importacao = False

    st.divider()

    col_importar, col_novo, col_editar, col_excluir = st.columns(4)

    with col_importar:
        if st.button("📥 Importar Excel", key="btn_importar", disabled=not pode_editar_materiais):
            st.session_state.mostrar_importacao = True

    with col_novo:
        if st.button("➕ Novo Material", disabled=not pode_editar_materiais):
            st.session_state.modo_material = "novo"
            st.session_state.material_em_edicao = None
            st.rerun()

    with col_editar:
        if st.button("✏️ Editar Material", key="btn_editar", disabled=not pode_editar_materiais):
            if materiais_selecionados.empty:
                st.warning("Selecione um item.")
            elif len(materiais_selecionados) > 1:
                st.warning("Selecione apenas um item.")
            else:
                st.session_state.modo_material = "editar"
                st.session_state.material_em_edicao = materiais_selecionados.iloc[0]
                st.rerun()

    with col_excluir:
        if st.button("🗑 Excluir Selecionados", key="btn_excluir", disabled=not pode_editar_materiais):
            if materiais_selecionados.empty:
                st.warning("Selecione ao menos um item.")
            else:
                st.session_state.confirmar_exclusao = True

    if st.session_state.confirmar_exclusao and not materiais_selecionados.empty:
        st.warning(f"⚠ Deseja excluir {len(materiais_selecionados)} item(ns)?")
        col_sim, col_nao = st.columns(2)

        with col_sim:
            if st.button("✅ Confirmar Exclusão", key="confirmar_delete"):
                for _, linha in materiais_selecionados.iterrows():
                    excluir_material(linha["Código Material"])
                st.session_state.confirmar_exclusao = False
                st.success("Itens excluídos com sucesso!")
                st.rerun()

        with col_nao:
            if st.button("❌ Cancelar Exclusão", key="cancelar_delete"):
                st.session_state.confirmar_exclusao = False
                st.rerun()

    if st.session_state.mostrar_importacao:
        st.divider()
        st.subheader("📥 Importação de Materiais")

        arquivo_excel = st.file_uploader(
            "Selecione o arquivo Excel",
            type=["xlsx"],
            key="upload_excel"
        )

        if arquivo_excel is not None:
            try:
                df_importacao = pd.read_excel(arquivo_excel)
                st.write("Pré-visualização")
                st.dataframe(df_importacao, use_container_width=True)

                if st.button("🚀 Importar Materiais", key="btn_confirmar_importacao"):
                    contador_inseridos = 0
                    contador_atualizados = 0
                    data_revisao_automatica = date.today().isoformat()

                    for _, linha in df_importacao.iterrows():
                        codigo_material = str(linha["Código Material"])
                        material_existente = buscar_material(codigo_material)

                        preco_coluna = (
                            "Preço Unitário Líquido"
                            if "Preço Unitário Líquido" in df_importacao.columns
                            else "Preço Revisado"
                        )

                        if material_existente:
                            atualizar_material(
                                codigo_material,
                                str(linha["Descrição"]),
                                str(linha["Material"]),
                                str(linha["Norma"]),
                                str(linha["NCM"]),
                                str(linha["Unidade"]),
                                str(linha["Código Interno Jundiaí"]),
                                str(linha["Código Interno Várzea"]),
                                float(linha[preco_coluna]),
                                data_revisao_automatica,
                                usuario_revisao_atual
                            )
                            contador_atualizados += 1
                        else:
                            inserir_material(
                                codigo_material,
                                str(linha["Descrição"]),
                                str(linha["Material"]),
                                str(linha["Norma"]),
                                str(linha["NCM"]),
                                str(linha["Unidade"]),
                                str(linha["Código Interno Jundiaí"]),
                                str(linha["Código Interno Várzea"]),
                                float(linha[preco_coluna]),
                                data_revisao_automatica,
                                usuario_revisao_atual
                            )
                            contador_inseridos += 1

                    st.success(
                        f"Importação concluída! {contador_inseridos} inseridos e {contador_atualizados} atualizados."
                    )
                    st.session_state.mostrar_importacao = False
                    st.rerun()

            except Exception as erro:
                st.error(f"Erro ao ler Excel: {erro}")

    if st.session_state.modo_material is not None:
        st.divider()
        material_em_edicao = st.session_state.get("material_em_edicao")

        if st.session_state.modo_material == "editar":
            st.subheader("✏️ Editar Material")
        else:
            st.subheader("➕ Novo Material")

        codigo_material = st.text_input(
            "Código Material KSB",
            value="" if material_em_edicao is None else material_em_edicao["Código Material"],
            disabled=(st.session_state.modo_material == "editar"),
            key="cad_codigo"
        )

        descricao = st.text_input(
            "Descrição",
            value="" if material_em_edicao is None else material_em_edicao["Descrição"],
            key="cad_descricao"
        )

        material = st.text_input(
            "Material",
            value="" if material_em_edicao is None else material_em_edicao["Material"],
            key="cad_material"
        )

        norma = st.text_input(
            "Norma",
            value="" if material_em_edicao is None else material_em_edicao["Norma"],
            key="cad_norma"
        )

        ncm = st.text_input(
            "NCM",
            value="" if material_em_edicao is None else material_em_edicao["NCM"],
            key="cad_ncm"
        )

        unidade_medida = st.text_input(
            "Unidade Medida",
            value="" if material_em_edicao is None else material_em_edicao["Unidade"],
            key="cad_unidade"
        )

        codigo_interno_jundiai = st.text_input(
            "Código Interno Jundiaí",
            value="" if material_em_edicao is None else material_em_edicao["Código Interno Jundiaí"],
            key="cad_jundiai"
        )

        codigo_interno_varzea = st.text_input(
            "Código Interno Várzea",
            value="" if material_em_edicao is None else material_em_edicao["Código Interno Várzea"],
            key="cad_varzea"
        )

        preco_unitario_liquido = st.number_input(
            "Preço Unitário Líquido",
            value=0.0 if material_em_edicao is None else float(material_em_edicao["Preço Unitário Líquido"]),
            format="%.2f",
            key="cad_preco_unitario_liquido"
        )

        data_revisao_automatica = date.today().isoformat()

        st.text_input(
            "Data Última Revisão",
            value=data_revisao_automatica,
            disabled=True,
            help="Data preenchida automaticamente pelo sistema no momento do salvamento.",
            key="cad_data_ultima_revisao_bloqueada"
        )

        usuario_ultima_revisao = st.text_input(
            "Usuário Última Revisão",
            value=str(usuario_revisao_atual),
            disabled=True,
            key="cad_usuario_ultima_revisao"
        )

        col_salvar, col_cancelar = st.columns(2)

        with col_salvar:
            if st.button("💾 Salvar", key="btn_salvar"):
                if st.session_state.modo_material == "novo":
                    inserir_material(
                        codigo_material,
                        descricao,
                        material,
                        norma,
                        ncm,
                        unidade_medida,
                        codigo_interno_jundiai,
                        codigo_interno_varzea,
                        preco_unitario_liquido,
                        data_revisao_automatica,
                        usuario_revisao_atual
                    )
                    st.success("Material cadastrado com sucesso!")
                else:
                    atualizar_material(
                        codigo_material,
                        descricao,
                        material,
                        norma,
                        ncm,
                        unidade_medida,
                        codigo_interno_jundiai,
                        codigo_interno_varzea,
                        preco_unitario_liquido,
                        data_revisao_automatica,
                        usuario_revisao_atual
                    )
                    st.success("Material atualizado com sucesso!")

                st.session_state.modo_material = None
                st.session_state.material_em_edicao = None
                st.rerun()

        with col_cancelar:
            if st.button("❌ Cancelar", key="btn_cancelar"):
                st.session_state.modo_material = None
                st.session_state.material_em_edicao = None
                st.rerun()

elif menu == "🏛 Regras Fiscais":

    st.title("🏛 Regras Fiscais")

    if "modo_regra" not in st.session_state:
        st.session_state.modo_regra = None

    if "regra_em_edicao" not in st.session_state:
        st.session_state.regra_em_edicao = None

    if "confirmar_exclusao_regra" not in st.session_state:
        st.session_state.confirmar_exclusao_regra = False

    lista_regras = listar_regras_fiscais()

    df_regras = pd.DataFrame(
        lista_regras,
        columns=["ID", "NCM", "ICMS", "IPI", "Observação", "Ativo"]
    )
    
    filtro_regra = st.text_input(
        "Pesquisar regra",
        placeholder="Palavra chave, material ou NCM",
        key="filtro_regra"
    )

    if filtro_regra:
        df_regras = df_regras[
            df_regras["Palavra Chave"].astype(str).str.contains(filtro_regra, case=False, na=False)
            | df_regras["Material"].astype(str).str.contains(filtro_regra, case=False, na=False)
            | df_regras["NCM"].astype(str).str.contains(filtro_regra, case=False, na=False)
        ]

    if not df_regras.empty:
        df_regras.insert(0, "Selecionar", False)
        tabela_regras = st.data_editor(df_regras, use_container_width=True, hide_index=True)
        regras_selecionadas = tabela_regras[tabela_regras["Selecionar"] == True]
    else:
        st.info("Nenhuma regra fiscal cadastrada.")
        regras_selecionadas = pd.DataFrame()

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
        col_sim, col_nao = st.columns(2)

        with col_sim:
            if st.button("✅ Confirmar Exclusão", key="confirmar_delete_regra"):
                for _, linha in regras_selecionadas.iterrows():
                    excluir_regra_fiscal(int(linha["ID"]))
                st.session_state.confirmar_exclusao_regra = False
                st.success("Regras excluídas com sucesso!")
                st.rerun()

        with col_nao:
            if st.button("❌ Cancelar Exclusão", key="cancelar_delete_regra"):
                st.session_state.confirmar_exclusao_regra = False
                st.rerun()

    if st.session_state.modo_regra is not None:
        regra_em_edicao = st.session_state.get("regra_em_edicao")
        st.divider()

        if st.session_state.modo_regra == "editar":
            st.subheader("✏️ Editar Regra Fiscal")
        else:
            st.subheader("➕ Nova Regra Fiscal")

        palavra_chave = st.text_input(
            "Palavra Chave",
            value="" if regra_em_edicao is None else regra_em_edicao["Palavra Chave"],
            key="rf_palavra"
        )

        material = st.text_input(
            "Material",
            value="" if regra_em_edicao is None else regra_em_edicao["Material"],
            key="rf_material"
        )

        ncm = st.text_input(
            "NCM",
            value="" if regra_em_edicao is None else regra_em_edicao["NCM"],
            key="rf_ncm"
        )

        aliquota_icms = st.number_input(
            "ICMS (%)",
            value=18.0 if regra_em_edicao is None else float(regra_em_edicao["ICMS"]),
            key="rf_icms"
        )

        aliquota_ipi = st.number_input(
            "IPI (%)",
            value=5.0 if regra_em_edicao is None else float(regra_em_edicao["IPI"]),
            key="rf_ipi"
        )

        observacao = st.text_area(
            "Observação",
            value="" if regra_em_edicao is None else regra_em_edicao["Observação"],
            key="rf_obs"
        )

        col_salvar, col_cancelar = st.columns(2)

        with col_salvar:
            if st.button("💾 Salvar Regra", key="btn_salvar_regra"):
                if st.session_state.modo_regra == "novo":
                    inserir_regra_fiscal(palavra_chave, material, ncm, aliquota_icms, aliquota_ipi, observacao, 1)
                else:
                    atualizar_regra_fiscal(int(regra_em_edicao["ID"]), palavra_chave, material, ncm, aliquota_icms, aliquota_ipi, observacao, 1)

                st.success("Regra fiscal cadastrada.")
                st.session_state.modo_regra = None
                st.rerun()

        with col_cancelar:
            if st.button("❌ Cancelar", key="btn_cancelar_regra"):
                st.session_state.modo_regra = None
                st.rerun()

# ====================================
# USUARIOS
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
                """
                UPDATE usuarios
                SET nome = %s,
                    usuario = %s,
                    perfil = %s,
                    ativo = %s
                WHERE id = %s
                """,
                (nome, usuario, perfil_usuario, ativo, id_usuario)
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
            cursor.execute("UPDATE usuarios SET ativo = %s WHERE id = %s", (ativo, id_usuario))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    def alterar_senha_usuario(id_usuario, nova_senha):
        conn = conectar()
        cursor = conn.cursor()
        try:
            cursor.execute("UPDATE usuarios SET senha = %s WHERE id = %s", (nova_senha, id_usuario))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    def usuario_selecionado_eh_logado(linha_usuario):
        return str(linha_usuario["Usuário"]) == str(st.session_state.usuario_logado)

    if "modo_usuario" not in st.session_state:
        st.session_state.modo_usuario = None

    if "usuario_em_edicao" not in st.session_state:
        st.session_state.usuario_em_edicao = None

    usuarios = listar_usuarios()

    df_usuarios = pd.DataFrame(usuarios, columns=["ID", "Nome", "Usuário", "Perfil", "Ativo"])

    if not df_usuarios.empty:
        df_usuarios["Status"] = df_usuarios["Ativo"].apply(lambda x: "Ativo" if int(x) == 1 else "Bloqueado")
        df_usuarios = df_usuarios[["ID", "Nome", "Usuário", "Perfil", "Status", "Ativo"]]

    filtro_usuario = st.text_input("Pesquisar usuário", placeholder="Nome, usuário ou perfil", key="filtro_usuario")

    if filtro_usuario and not df_usuarios.empty:
        pesquisa_usuario = filtro_usuario.strip()
        df_usuarios = df_usuarios[
            df_usuarios["Nome"].astype(str).str.contains(pesquisa_usuario, case=False, na=False)
            | df_usuarios["Usuário"].astype(str).str.contains(pesquisa_usuario, case=False, na=False)
            | df_usuarios["Perfil"].astype(str).str.contains(pesquisa_usuario, case=False, na=False)
        ]

    if df_usuarios.empty:
        st.info("Nenhum usuário cadastrado.")
        usuarios_selecionados = pd.DataFrame()
    else:
        df_usuarios.insert(0, "Selecionar", False)
        tabela_usuarios = st.data_editor(
            df_usuarios,
            use_container_width=True,
            hide_index=True,
            disabled=["ID", "Nome", "Usuário", "Perfil", "Status", "Ativo"],
            key="tabela_usuarios"
        )
        usuarios_selecionados = tabela_usuarios[tabela_usuarios["Selecionar"] == True]

    st.divider()

    col_novo, col_editar, col_status, col_senha, col_excluir = st.columns(5)

    with col_novo:
        if st.button("➕ Novo Usuário", key="btn_novo_usuario"):
            st.session_state.modo_usuario = "novo"
            st.session_state.usuario_em_edicao = None
            st.rerun()

    with col_editar:
        if st.button("✏️ Editar Usuário", key="btn_editar_usuario"):
            if usuarios_selecionados.empty:
                st.warning("Selecione um usuário.")
            elif len(usuarios_selecionados) > 1:
                st.warning("Selecione apenas um usuário.")
            else:
                st.session_state.modo_usuario = "editar"
                st.session_state.usuario_em_edicao = usuarios_selecionados.iloc[0]
                st.rerun()

    with col_status:
        if st.button("🔒 Bloquear/Ativar", key="btn_status_usuario"):
            if usuarios_selecionados.empty:
                st.warning("Selecione um usuário.")
            elif len(usuarios_selecionados) > 1:
                st.warning("Selecione apenas um usuário.")
            else:
                linha_usuario = usuarios_selecionados.iloc[0]
                if usuario_selecionado_eh_logado(linha_usuario):
                    st.warning("Você não pode bloquear o próprio usuário logado.")
                else:
                    novo_status = 0 if int(linha_usuario["Ativo"]) == 1 else 1
                    alterar_status_usuario(int(linha_usuario["ID"]), novo_status)
                    st.success("Status alterado com sucesso.")
                    st.rerun()

    with col_senha:
        if st.button("🔑 Redefinir Senha", key="btn_redefinir_senha"):
            if usuarios_selecionados.empty:
                st.warning("Selecione um usuário.")
            elif len(usuarios_selecionados) > 1:
                st.warning("Selecione apenas um usuário.")
            else:
                st.session_state.modo_usuario = "senha"
                st.session_state.usuario_em_edicao = usuarios_selecionados.iloc[0]
                st.rerun()

    with col_excluir:
        if st.button("🗑️ Excluir Usuário", key="btn_excluir_usuario"):
            if usuarios_selecionados.empty:
                st.warning("Selecione um usuário.")
            elif len(usuarios_selecionados) > 1:
                st.warning("Selecione apenas um usuário.")
            else:
                linha_usuario = usuarios_selecionados.iloc[0]
                if usuario_selecionado_eh_logado(linha_usuario):
                    st.warning("Você não pode excluir o próprio usuário logado.")
                else:
                    st.session_state.modo_usuario = "excluir"
                    st.session_state.usuario_em_edicao = linha_usuario
                    st.rerun()

    if st.session_state.modo_usuario in ["novo", "editar"]:
        st.divider()
        usuario_em_edicao = st.session_state.get("usuario_em_edicao")
        st.subheader("➕ Novo Usuário" if st.session_state.modo_usuario == "novo" else "✏️ Editar Usuário")

        with st.form("form_usuario"):
            nome = st.text_input("Nome", value="" if usuario_em_edicao is None else str(usuario_em_edicao["Nome"]))
            usuario = st.text_input("Usuário", value="" if usuario_em_edicao is None else str(usuario_em_edicao["Usuário"]))

            senha = ""
            if st.session_state.modo_usuario == "novo":
                senha = st.text_input("Senha", type="password")

            perfis = ["ADMIN", "VENDEDORA", "PROCESSISTA"]
            perfil_padrao = 0
            if usuario_em_edicao is not None:
                perfil_atual = str(usuario_em_edicao["Perfil"])
                if perfil_atual in perfis:
                    perfil_padrao = perfis.index(perfil_atual)

            perfil_novo = st.selectbox("Perfil", perfis, index=perfil_padrao)

            status_opcoes = ["Ativo", "Bloqueado"]
            status_index = 0
            if usuario_em_edicao is not None and int(usuario_em_edicao["Ativo"]) == 0:
                status_index = 1

            status = st.selectbox("Status", status_opcoes, index=status_index)

            col_salvar_usuario, col_cancelar_usuario = st.columns(2)

            with col_salvar_usuario:
                salvar_usuario = st.form_submit_button("💾 Salvar")

            with col_cancelar_usuario:
                cancelar_usuario = st.form_submit_button("❌ Cancelar")

            if salvar_usuario:
                if not nome or not usuario:
                    st.warning("Preencha nome e usuário.")
                elif st.session_state.modo_usuario == "novo" and not senha:
                    st.warning("Preencha a senha.")
                else:
                    ativo = 1 if status == "Ativo" else 0
                    if st.session_state.modo_usuario == "editar" and usuario_selecionado_eh_logado(usuario_em_edicao) and ativo == 0:
                        st.warning("Você não pode bloquear o próprio usuário logado.")
                    else:
                        try:
                            if st.session_state.modo_usuario == "novo":
                                inserir_usuario(nome, usuario, senha, perfil_novo)
                                usuarios_atualizados = listar_usuarios()
                                for u in usuarios_atualizados:
                                    if str(u[2]) == str(usuario):
                                        alterar_status_usuario(int(u[0]), ativo)
                                        break
                                st.success("Usuário cadastrado com sucesso.")
                            else:
                                atualizar_usuario(int(usuario_em_edicao["ID"]), nome, usuario, perfil_novo, ativo)
                                st.success("Usuário atualizado com sucesso.")

                            st.session_state.modo_usuario = None
                            st.session_state.usuario_em_edicao = None
                            st.rerun()
                        except Exception as erro:
                            st.error("Erro ao salvar usuário.")
                            st.exception(erro)

            if cancelar_usuario:
                st.session_state.modo_usuario = None
                st.session_state.usuario_em_edicao = None
                st.rerun()

    elif st.session_state.modo_usuario == "senha":
        st.divider()
        usuario_em_edicao = st.session_state.get("usuario_em_edicao")
        st.subheader("🔑 Redefinir Senha")
        st.write(f"Usuário selecionado: **{usuario_em_edicao['Usuário']}**")

        with st.form("form_redefinir_senha"):
            nova_senha = st.text_input("Nova senha", type="password")
            confirmar_senha = st.text_input("Confirmar nova senha", type="password")

            col_salvar_senha, col_cancelar_senha = st.columns(2)

            with col_salvar_senha:
                salvar_senha = st.form_submit_button("💾 Salvar nova senha")

            with col_cancelar_senha:
                cancelar_senha = st.form_submit_button("❌ Cancelar")

            if salvar_senha:
                if not nova_senha:
                    st.warning("Informe a nova senha.")
                elif nova_senha != confirmar_senha:
                    st.warning("As senhas não conferem.")
                else:
                    alterar_senha_usuario(int(usuario_em_edicao["ID"]), nova_senha)
                    st.success("Senha redefinida com sucesso.")
                    st.session_state.modo_usuario = None
                    st.session_state.usuario_em_edicao = None
                    st.rerun()

            if cancelar_senha:
                st.session_state.modo_usuario = None
                st.session_state.usuario_em_edicao = None
                st.rerun()

    elif st.session_state.modo_usuario == "excluir":
        st.divider()
        usuario_em_edicao = st.session_state.get("usuario_em_edicao")
        st.warning(f"Confirma excluir o usuário {usuario_em_edicao['Usuário']}?")

        col_confirmar_excluir, col_cancelar_excluir = st.columns(2)

        with col_confirmar_excluir:
            if st.button("✅ Confirmar Exclusão", key="confirmar_excluir_usuario"):
                excluir_usuario(int(usuario_em_edicao["ID"]))
                st.success("Usuário excluído com sucesso.")
                st.session_state.modo_usuario = None
                st.session_state.usuario_em_edicao = None
                st.rerun()

        with col_cancelar_excluir:
            if st.button("❌ Cancelar Exclusão", key="cancelar_excluir_usuario"):
                st.session_state.modo_usuario = None
                st.session_state.usuario_em_edicao = None
                st.rerun()

# ====================================
# FERRAMENTAS ADMINISTRATIVAS
# ====================================

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

        if confirmacao == "MIGRAR":
            if st.button("🚀 Executar Migração"):
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

# ====================================
# HISTORICO
# ====================================

elif menu == "📋 Histórico de Auditorias":

    st.title("📋 Histórico de Auditorias")
    st.info("Módulo em desenvolvimento")
