import streamlit as st

from migrar_sqlite_para_postgres import migrar


st.set_page_config(
    page_title="Migrar Banco",
    page_icon="🗄️",
    layout="centered",
)

st.title("🗄️ Migração do Banco")

st.warning(
    "Esta página é temporária. Use apenas uma vez para copiar os dados do database.db para o PostgreSQL/Neon."
)

st.write("Origem: SQLite `database.db`")
st.write("Destino: PostgreSQL configurado nas variáveis de ambiente")

limpar_destino = st.checkbox(
    "Limpar dados atuais do PostgreSQL antes de migrar",
    value=False,
)

confirmacao = st.text_input(
    "Digite MIGRAR para liberar o botão",
    value="",
)

if confirmacao == "MIGRAR":
    if st.button("🚀 Executar migração agora"):
        try:
            with st.spinner("Migrando dados..."):
                totais = migrar(
                    sqlite_path="database.db",
                    limpar=limpar_destino,
                )

            st.success("Migração concluída com sucesso.")

            for tabela, total in totais.items():
                st.write(f"{tabela}: {total} registro(s) migrado(s)")

        except Exception as erro:
            st.error("Erro ao executar migração.")
            st.exception(erro)
else:
    st.info("Digite MIGRAR acima para habilitar a execução.")
