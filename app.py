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
    localizar_regra_fiscal    
)

import streamlit as st
import pandas as pd

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
# MENU
# ====================================

menu = st.sidebar.radio(

    "Menu",

    [

        "📄 Análise de Pedidos KSB",

        "📦 Itens Cadastrados",

         "🏛 Regras Fiscais",

        "📋 Histórico de Auditorias"

    ]
)

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

                    todas_analises.append(
                        df_analise
                    )

                    progresso = int(
                        (
                            (idx + 1)
                            / len(uploaded_files)
                        )
                        * 100
                    )

                    progress.progress(
                        progresso
                    )

            df_final = pd.concat(
                todos_dados,
                ignore_index=True
            )

            df_analise_final = pd.concat(
                todas_analises,
                ignore_index=True
            )

            total_itens = len(
                df_analise_final
            )

            total_ok = len(

                df_analise_final[
                    df_analise_final["Status"]
                    == "OK"
                ]

            )

            total_div = len(

                df_analise_final[
                    df_analise_final["Status"]
                    == "DIVERGENTE"
                ]

            )

            col1, col2, col3 = st.columns(3)

            col1.metric(
                "Itens Processados",
                total_itens
            )

            col2.metric(
                "Itens OK",
                total_ok
            )

            col3.metric(
                "Itens Divergentes",
                total_div
            )

            st.divider()

            st.subheader(
                "📋 Auditoria"
            )

            def colorir_status(val):

                if val == "OK":

                    return (
                        "background-color: "
                        "#b6ffb6"
                    )

                if val == "DIVERGENTE":

                    return (
                        "background-color: "
                        "#ffb6b6"
                    )

                return ""

            df_analise_final[
                "Divergencias"
            ] = (

                df_analise_final[
                    "Divergencias"
                ]
                .astype(str)
                .str.replace(
                    "|",
                    "\n"
                )

            )

            st.data_editor(

                df_analise_final.style.map(
                    colorir_status,
                    subset=["Status"]
                ),

                use_container_width=True,

                height=400

            )

            st.divider()

            st.subheader(
                "📦 Dados Extraídos"
            )

            st.dataframe(
                df_final,
                use_container_width=True
            )

            csv = (
                df_final
                .to_csv(
                    index=False,
                    sep=";"
                )
                .encode(
                    "utf-8-sig"
                )
            )

            st.download_button(

                label="📥 Download CSV",

                data=csv,

                file_name=
                "pedidos_extraidos.csv",

                mime="text/csv"

            )

            excel_path = (
                "pedidos_extraidos.xlsx"
            )

            with pd.ExcelWriter(

                excel_path,

                engine="openpyxl"

            ) as writer:

                df_final.to_excel(
                    writer,
                    index=False,
                    sheet_name="Pedidos"
                )

                df_analise_final.to_excel(
                    writer,
                    index=False,
                    sheet_name="Auditoria"
                )

            with open(
                excel_path,
                "rb"
            ) as f:

                st.download_button(

                    label="📥 Download Excel",

                    data=f,

                    file_name=
                    "pedidos_extraidos.xlsx",

                    mime=(
                        "application/"
                        "vnd.openxmlformats-"
                        "officedocument."
                        "spreadsheetml.sheet"
                    )

                )

            st.success(
                "Processamento concluído com sucesso!"
            )

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
            "Preço Revisado",
            "Última Revisão"

        ]

    )

    # ====================================
    # FILTROS
    # ====================================

    filtro_material = st.text_input(
                "Pesquisar material",
                placeholder="Código, descrição ou código interno..."
            )

    # ====================================
    # FILTRO PESQUISA
    # ====================================

    if filtro_material:

        pesquisa = filtro_material.strip()

        df_materiais = df_materiais[

            df_materiais["Código Material"]
            .astype(str)
            .str.contains(
                pesquisa,
                case=False,
                na=False
            )

            |

            df_materiais["Descrição"]
            .astype(str)
            .str.contains(
                pesquisa,
                case=False,
                na=False
            )

            |

            df_materiais["Código Interno Jundiaí"]
            .astype(str)
            .str.contains(
                pesquisa,
                case=False,
                na=False
            )

            |

            df_materiais["Código Interno Várzea"]
            .astype(str)
            .str.contains(
                pesquisa,
                case=False,
                na=False
            )

        ]

    # ====================================
    # TABELA
    # ====================================

    st.subheader("Itens Cadastrados")

    if df_materiais.empty:

        st.info(
            "Nenhum item cadastrado."
        )
        
        materiais_selecionados = pd.DataFrame()
        st.session_state.confirmar_exclusao = False
    

    else:

        df_materiais.insert(
            0,
            "Selecionar",
            False
        )

        tabela_materiais = st.data_editor(

            df_materiais,

            use_container_width=True,

            hide_index=True

        )

    
        materiais_selecionados = tabela_materiais[
        tabela_materiais["Selecionar"] == True
    ]
    


    # ====================================
    # BOTOES
    # ====================================

    if "modo_material" not in st.session_state:
        st.session_state.modo_material = None

    if "confirmar_exclusao" not in st.session_state:
        st.session_state.confirmar_exclusao = False

    if "mostrar_importacao" not in st.session_state:
        st.session_state.mostrar_importacao = False
    
    st.divider()

    col_importar, col_novo, col_editar, col_excluir = st.columns(4)

    with col_importar:

     if st.button(
        "📥 Importar Excel",
        key="btn_importar"
    ):

        st.session_state.mostrar_importacao = True
    
    with col_novo:

        if st.button(
            "➕ Novo Material"
        ):

            st.session_state.modo_material = "novo"

            st.session_state.material_em_edicao = None

            st.rerun()


    with col_editar:

            
            if st.button(
                "✏️ Editar Material",
                key="btn_editar"
            ):

                if materiais_selecionados.empty:

                    st.warning(
                        "Selecione um item."
                    )

                elif len(materiais_selecionados) > 1:

                    st.warning(
                        "Selecione apenas um item."
                    )

                else:

                    st.session_state.modo_material = "editar"

                    st.session_state.material_em_edicao = (
                        materiais_selecionados.iloc[0]
                    )

                    st.rerun()
            

     

    with col_excluir:

        if st.button(
            "🗑 Excluir Selecionados",
            key="btn_excluir"
        ):

            if materiais_selecionados.empty:

                st.warning(
                    "Selecione ao menos um item."
                )

            else:

                st.session_state.confirmar_exclusao = True

                        
    # ====================================
    # CONFIRMAÇÃO EXCLUSÃO
    # ====================================

    if (
                            st.session_state.confirmar_exclusao
                            and not materiais_selecionados.empty
                        ):

                            st.warning(
                                f"⚠ Deseja excluir {len(materiais_selecionados)} item(ns)?"
                            )

                            col_sim, col_nao = st.columns(2)

                            with col_sim:

                                if st.button(
                                    "✅ Confirmar Exclusão",
                                    key="confirmar_delete"
                                ):

                                    for _, linha in materiais_selecionados.iterrows():

                                        excluir_material(
                                            linha["Código Material"]
                                        )

                                    st.session_state.confirmar_exclusao = False

                                    st.success(
                                        "Itens excluídos com sucesso!"
                                    )

                                    st.rerun()

                            with col_nao:

                                if st.button(
                                    "❌ Cancelar Exclusão",
                                    key="cancelar_delete"
                                ):

                                    st.session_state.confirmar_exclusao = False

                                    st.rerun()
                    
    
    # ====================================
    # IMPORTAÇÃO EXCEL
    # ====================================

    if st.session_state.mostrar_importacao:

        st.divider()

        st.subheader(
            "📥 Importação de Materiais"
        )

        arquivo_excel = st.file_uploader(
            "Selecione o arquivo Excel",
            type=["xlsx"],
            key="upload_excel"
        )

        if arquivo_excel is not None:

            try:

                df_importacao = pd.read_excel(
                    arquivo_excel
                )

                st.write(
                    "Pré-visualização"
                )

                st.dataframe(
                    df_importacao,
                    use_container_width=True
                )

                col_importar_excel, col_cancelar_excel = st.columns(2)

                with col_importar_excel:

                        
                        if st.button(
                            "🚀 Importar Materiais",
                            key="btn_confirmar_importacao"
                        ):

                            contador_inseridos = 0
                            contador_atualizados = 0

                            for _, linha in df_importacao.iterrows():

                                codigo_material = str(
                                    linha["Código Material"]
                                )

                                material_existente = buscar_material(
                                    codigo_material
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

                                        float(linha["Preço Revisado"]),

                                        str(linha["Data Revisão"])

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

                                        float(linha["Preço Revisado"]),

                                        str(linha["Data Revisão"])

                                    )

                                    contador_inseridos += 1

                            st.success(
                                f"Importação concluída! "
                                f"{contador_inseridos} inseridos e "
                                f"{contador_atualizados} atualizados."
                            )

                            st.session_state.mostrar_importacao = False

                            st.rerun()
                        


            except Exception as erro:

                st.error(
                    f"Erro ao ler Excel: {erro}"
                )
    

    
    # ====================================
    # FORMULARIO
    # ====================================

    if st.session_state.modo_material is not None:

        st.divider()

        material_em_edicao = st.session_state.get(
            "material_em_edicao"
        )

        if st.session_state.modo_material == "editar":

            st.subheader("✏️ Editar Material")

        else:

            st.subheader("➕ Novo Material")

        codigo_material = st.text_input(

            "Código Material KSB",

            value=""
            if material_em_edicao is None
            else material_em_edicao["Código Material"],

            disabled=(
                st.session_state.modo_material
                == "editar"
            ),

            key="cad_codigo"

        )

        descricao = st.text_input(
            "Descrição",
            value=""
            if material_em_edicao is None
            else material_em_edicao["Descrição"],
            key="cad_descricao"
        )

        material = st.text_input(
            "Material",
            value=""
            if material_em_edicao is None
            else material_em_edicao["Material"],
            key="cad_material"
        )

        norma = st.text_input(
            "Norma",
            value=""
            if material_em_edicao is None
            else material_em_edicao["Norma"],
            key="cad_norma"
        )

        ncm = st.text_input(
            "NCM",
            value=""
            if material_em_edicao is None
            else material_em_edicao["NCM"],
            key="cad_ncm"
        )

        unidade_medida = st.text_input(
            "Unidade Medida",
            value=""
            if material_em_edicao is None
            else material_em_edicao["Unidade"],
            key="cad_unidade"
        )

        codigo_interno_jundiai = st.text_input(
            "Código Interno Jundiaí",
            value=""
            if material_em_edicao is None
            else material_em_edicao["Código Interno Jundiaí"],
            key="cad_jundiai"
        )

        codigo_interno_varzea = st.text_input(
            "Código Interno Várzea",
            value=""
            if material_em_edicao is None
            else material_em_edicao["Código Interno Várzea"],
            key="cad_varzea"
        )

        preco_revisado = st.number_input(
            "Preço Revisado",
            value=0.0
            if material_em_edicao is None
            else float(material_em_edicao["Preço Revisado"]),
            format="%.2f",
            key="cad_preco"
        )

        data_revisao = st.date_input(
            "Data Última Revisão",
            key="cad_data"
        )

        col_salvar, col_cancelar = st.columns(2)

        with col_salvar:

            if st.button(
                "💾 Salvar",
                key="btn_salvar"
            ):

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
                        preco_revisado,
                        str(data_revisao)

                    )

                    st.success(
                        "Material cadastrado com sucesso!"
                    )

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
                        preco_revisado,
                        str(data_revisao)

                    )

                    st.success(
                        "Material atualizado com sucesso!"
                    )

                st.session_state.modo_material = None

                st.session_state.material_em_edicao = None

                st.rerun()

        with col_cancelar:

            if st.button(
                "❌ Cancelar",
                key="btn_cancelar"
            ):

                st.session_state.modo_material = None

                st.session_state.material_em_edicao = None

                st.rerun()
    

        
elif menu == "🏛 Regras Fiscais":

            st.title(
                "🏛 Regras Fiscais"
            )

            # ====================================
            # SESSION STATE
            # ====================================

            if "modo_regra" not in st.session_state:
                st.session_state.modo_regra = None

            if "regra_em_edicao" not in st.session_state:
                st.session_state.regra_em_edicao = None
                
            if "confirmar_exclusao_regra" not in st.session_state:
                    st.session_state.confirmar_exclusao_regra = False

            # ====================================
            # CONSULTA BANCO
            # ====================================

            lista_regras = listar_regras_fiscais()

            df_regras = pd.DataFrame(

                lista_regras,

                columns=[

                    "ID",
                    "Palavra Chave",
                    "Material",
                    "NCM",
                    "ICMS",
                    "IPI",
                    "Observação",
                    "Ativo"

                ]

            )

            # ====================================
            # PESQUISA
            # ====================================

            filtro_regra = st.text_input(
                "Pesquisar regra",
                placeholder="Palavra chave, material ou NCM",
                key="filtro_regra"
            )

            if filtro_regra:

                df_regras = df_regras[

                    df_regras["Palavra Chave"]
                    .astype(str)
                    .str.contains(
                        filtro_regra,
                        case=False,
                        na=False
                    )

                    |

                    df_regras["Material"]
                    .astype(str)
                    .str.contains(
                        filtro_regra,
                        case=False,
                        na=False
                    )

                    |

                    df_regras["NCM"]
                    .astype(str)
                    .str.contains(
                        filtro_regra,
                        case=False,
                        na=False
                    )

                ]

            # ====================================
            # TABELA
            # ====================================

            if not df_regras.empty:

                df_regras.insert(
                    0,
                    "Selecionar",
                    False
                )

                tabela_regras = st.data_editor(

                    df_regras,

                    use_container_width=True,

                    hide_index=True

                )

                regras_selecionadas = tabela_regras[
                    tabela_regras["Selecionar"] == True
                ]

            else:

                st.info(
                    "Nenhuma regra fiscal cadastrada."
                )

                regras_selecionadas = pd.DataFrame()

            st.divider()

            # ====================================
            # BOTÕES
            # ====================================

            col_nova, col_editar, col_excluir = st.columns(3)

            with col_nova:

                if st.button(
                    "➕ Nova Regra",
                    key="btn_nova_regra"
                ):
                    
                    st.session_state.modo_regra = "novo"

                    st.session_state.regra_em_edicao = None

                    st.rerun()

            with col_editar:

                    if st.button(
                        "✏️ Editar Regra",
                        key="btn_editar_regra"
                    ):

                        if regras_selecionadas.empty:

                            st.warning(
                                "Selecione uma regra."
                            )

                        elif len(regras_selecionadas) > 1:

                            st.warning(
                                "Selecione apenas uma regra."
                            )

                        else:

                            st.session_state.modo_regra = "editar"

                            st.session_state.regra_em_edicao = (
                                regras_selecionadas.iloc[0]
                            )

                            st.rerun()

            with col_excluir:

                    if st.button(
                        "🗑 Excluir Regra",
                        key="btn_excluir_regra"
                    ):

                        if regras_selecionadas.empty:

                            st.warning(
                                "Selecione ao menos uma regra."
                            )

                        else:

                            st.session_state.confirmar_exclusao_regra = True
           
            # ====================================
            # CONFIRMAÇÃO EXCLUSÃO REGRA
            # ====================================

            if (
                st.session_state.confirmar_exclusao_regra
                and not regras_selecionadas.empty
            ):

                st.warning(
                    f"⚠ Deseja excluir {len(regras_selecionadas)} regra(s)?"
                )

                col_sim, col_nao = st.columns(2)

                with col_sim:

                    if st.button(
                        "✅ Confirmar Exclusão",
                        key="confirmar_delete_regra"
                    ):

                        for _, linha in regras_selecionadas.iterrows():

                            excluir_regra_fiscal(
                                int(linha["ID"])
                            )

                        st.session_state.confirmar_exclusao_regra = False

                        st.success(
                            "Regras excluídas com sucesso!"
                        )

                        st.rerun()

                with col_nao:

                    if st.button(
                        "❌ Cancelar Exclusão",
                        key="cancelar_delete_regra"
                    ):

                        st.session_state.confirmar_exclusao_regra = False

                        st.rerun()

            # ====================================
            # FORMULÁRIO REGRA FISCAL
            # ====================================

            if st.session_state.modo_regra is not None:
                regra_em_edicao = st.session_state.get(
                    "regra_em_edicao"
                )

                st.divider()

                if st.session_state.modo_regra == "editar":

                    st.subheader(
                        "✏️ Editar Regra Fiscal"
                    )

                else:

                    st.subheader(
                        "➕ Nova Regra Fiscal"
                    )

                palavra_chave = st.text_input(

                    "Palavra Chave",

                    value=""
                    if regra_em_edicao is None
                    else regra_em_edicao["Palavra Chave"],

                    key="rf_palavra"

                )

                material = st.text_input(

                    "Material",

                    value=""
                    if regra_em_edicao is None
                    else regra_em_edicao["Material"],

                    key="rf_material"

                )

                ncm = st.text_input(

                    "NCM",

                    value=""
                    if regra_em_edicao is None
                    else regra_em_edicao["NCM"],

                    key="rf_ncm"

                )

                aliquota_icms = st.number_input(

                    "ICMS (%)",

                    value=18.0
                    if regra_em_edicao is None
                    else float(regra_em_edicao["ICMS"]),

                    key="rf_icms"

                )

                aliquota_ipi = st.number_input(

                    "IPI (%)",

                    value=5.0
                    if regra_em_edicao is None
                    else float(regra_em_edicao["IPI"]),

                    key="rf_ipi"

                )

                observacao = st.text_area(

                    "Observação",

                    value=""
                    if regra_em_edicao is None
                    else regra_em_edicao["Observação"],

                    key="rf_obs"

                )

                col_salvar, col_cancelar = st.columns(2)

                with col_salvar:

                    if st.button(
                        "💾 Salvar Regra",
                        key="btn_salvar_regra"
                    ):

                        if st.session_state.modo_regra == "novo":

                            inserir_regra_fiscal(

                                palavra_chave,
                                material,
                                ncm,
                                aliquota_icms,
                                aliquota_ipi,
                                observacao,
                                1

                            )

                        else:

                            atualizar_regra_fiscal(

                                int(regra_em_edicao["ID"]),

                                palavra_chave,
                                material,
                                ncm,
                                aliquota_icms,
                                aliquota_ipi,
                                observacao,
                                1

                            )

                        st.success(
                            "Regra fiscal cadastrada."
                        )

                        st.session_state.modo_regra = None

                        st.rerun()

                with col_cancelar:

                    if st.button(
                        "❌ Cancelar",
                        key="btn_cancelar_regra"
                    ):

                        st.session_state.modo_regra = None

                        st.rerun()
        


    



# ====================================
# HISTORICO
# ====================================

elif menu == "📋 Histórico de Auditorias":

    st.title(
        "📋 Histórico de Auditorias"
    )

    st.info(
        "Módulo em desenvolvimento"
    )
