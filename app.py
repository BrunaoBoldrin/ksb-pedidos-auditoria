import streamlit as st
import pandas as pd

from parser import processar_pdf

# ====================================
# CONFIG PAGINA
# ====================================

st.set_page_config(page_title="Analisador de Pedidos", page_icon="📄", layout="wide")

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
# TITULO
# ====================================

st.title("📄 Analisador de Pedidos KSB")

st.write("Sistema de extração e auditoria automática de pedidos.")

# ====================================
# UPLOAD
# ====================================

uploaded_files = st.file_uploader(
    "Selecione os PDFs", type=["pdf"], accept_multiple_files=True
)

# ====================================
# PROCESSAMENTO
# ====================================

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

                progresso = int(((idx + 1) / len(uploaded_files)) * 100)

                progress.progress(progresso)

        # ====================================
        # DATAFRAMES FINAIS
        # ====================================

        df_final = pd.concat(todos_dados, ignore_index=True)

        df_analise_final = pd.concat(todas_analises, ignore_index=True)

        # ====================================
        # METRICAS
        # ====================================

        total_itens = len(df_analise_final)

        total_ok = len(df_analise_final[df_analise_final["Status"] == "OK"])

        total_div = len(df_analise_final[df_analise_final["Status"] == "DIVERGENTE"])

        # ====================================
        # CARDS
        # ====================================

        col1, col2, col3 = st.columns(3)

        col1.metric("Itens Processados", total_itens)

        col2.metric("Itens OK", total_ok)

        col3.metric("Itens Divergentes", total_div)

        st.divider()

        # ====================================
        # ANALISE
        # ====================================

        st.subheader("📋 Auditoria")

        def colorir_status(val):
            if val == "OK":
                return "background-color: #b6ffb6"

            if val == "DIVERGENTE":
                return "background-color: #ffb6b6"

            return ""

        # ====================================
        # FORMATA DIVERGENCIAS
        # ====================================

        df_analise_final["Divergencias"] = (
            df_analise_final["Divergencias"].astype(str).str.replace("|", "\n")
        )

        # ====================================
        # TABELA
        # ====================================

        st.data_editor(
            df_analise_final.style.map(colorir_status, subset=["Status"]),
            use_container_width=True,
            height=400,
        )

        st.divider()

        # ====================================
        # DADOS EXTRAIDOS
        # ====================================

        st.subheader("📦 Dados Extraídos")

        st.dataframe(df_final, use_container_width=True)

        # ====================================
        # CSV
        # ====================================

        csv = df_final.to_csv(index=False, sep=";").encode("utf-8-sig")

        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name="pedidos_extraidos.csv",
            mime="text/csv",
        )

        # ====================================
        # EXCEL
        # ====================================

        excel_path = "pedidos_extraidos.xlsx"

        with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
            df_final.to_excel(writer, index=False, sheet_name="Pedidos")

            df_analise_final.to_excel(writer, index=False, sheet_name="Auditoria")

        with open(excel_path, "rb") as f:
            st.download_button(
                label="📥 Download Excel",
                data=f,
                file_name="pedidos_extraidos.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        st.success("Processamento concluído com sucesso!")
