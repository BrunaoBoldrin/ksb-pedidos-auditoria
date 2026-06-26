import pandas as pd
import streamlit as st

from database import conectar, inserir_usuario, listar_usuarios, excluir_usuario


st.set_page_config(
    page_title="CRUD de Usuários",
    page_icon="👤",
    layout="wide",
)


def exigir_admin():
    if st.session_state.get("perfil_usuario") != "ADMIN":
        st.error("Acesso negado. Esta área é exclusiva para ADMIN.")
        st.stop()


def atualizar_usuario(id_usuario, nome, usuario, perfil, ativo):
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
            (nome, usuario, perfil, ativo, id_usuario),
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
        cursor.execute(
            "UPDATE usuarios SET ativo = %s WHERE id = %s",
            (ativo, id_usuario),
        )
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
        cursor.execute(
            "UPDATE usuarios SET senha = %s WHERE id = %s",
            (nova_senha, id_usuario),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def usuario_logado_eh_o_mesmo(usuario_linha):
    return str(usuario_linha.get("Usuário")) == str(st.session_state.get("usuario_logado"))


exigir_admin()

st.title("👤 CRUD de Usuários")
st.caption("Cadastro, edição, bloqueio, desbloqueio, redefinição de senha e exclusão de usuários.")

if "modo_crud_usuario" not in st.session_state:
    st.session_state.modo_crud_usuario = None

if "usuario_crud_edicao" not in st.session_state:
    st.session_state.usuario_crud_edicao = None

usuarios = listar_usuarios()

df_usuarios = pd.DataFrame(
    usuarios,
    columns=["ID", "Nome", "Usuário", "Perfil", "Ativo"],
)

if df_usuarios.empty:
    st.info("Nenhum usuário cadastrado.")
    usuarios_selecionados = pd.DataFrame()
else:
    df_usuarios["Status"] = df_usuarios["Ativo"].apply(
        lambda valor: "Ativo" if int(valor) == 1 else "Bloqueado"
    )
    df_tabela = df_usuarios[["ID", "Nome", "Usuário", "Perfil", "Status", "Ativo"]].copy()
    df_tabela.insert(0, "Selecionar", False)

    tabela_usuarios = st.data_editor(
        df_tabela,
        use_container_width=True,
        hide_index=True,
        disabled=["ID", "Nome", "Usuário", "Perfil", "Status", "Ativo"],
    )

    usuarios_selecionados = tabela_usuarios[tabela_usuarios["Selecionar"] == True]

st.divider()

col_novo, col_editar, col_status, col_senha, col_excluir = st.columns(5)

with col_novo:
    if st.button("➕ Novo Usuário"):
        st.session_state.modo_crud_usuario = "novo"
        st.session_state.usuario_crud_edicao = None
        st.rerun()

with col_editar:
    if st.button("✏️ Editar Usuário"):
        if usuarios_selecionados.empty:
            st.warning("Selecione um usuário.")
        elif len(usuarios_selecionados) > 1:
            st.warning("Selecione apenas um usuário.")
        else:
            st.session_state.modo_crud_usuario = "editar"
            st.session_state.usuario_crud_edicao = usuarios_selecionados.iloc[0].to_dict()
            st.rerun()

with col_status:
    if st.button("🔒 Bloquear/Ativar"):
        if usuarios_selecionados.empty:
            st.warning("Selecione um usuário.")
        elif len(usuarios_selecionados) > 1:
            st.warning("Selecione apenas um usuário.")
        else:
            linha = usuarios_selecionados.iloc[0].to_dict()
            if usuario_logado_eh_o_mesmo(linha):
                st.warning("Você não pode bloquear o próprio usuário logado.")
            else:
                novo_status = 0 if int(linha["Ativo"]) == 1 else 1
                alterar_status_usuario(int(linha["ID"]), novo_status)
                st.success("Status do usuário alterado com sucesso.")
                st.rerun()

with col_senha:
    if st.button("🔑 Redefinir Senha"):
        if usuarios_selecionados.empty:
            st.warning("Selecione um usuário.")
        elif len(usuarios_selecionados) > 1:
            st.warning("Selecione apenas um usuário.")
        else:
            st.session_state.modo_crud_usuario = "senha"
            st.session_state.usuario_crud_edicao = usuarios_selecionados.iloc[0].to_dict()
            st.rerun()

with col_excluir:
    if st.button("🗑️ Excluir Usuário"):
        if usuarios_selecionados.empty:
            st.warning("Selecione um usuário.")
        elif len(usuarios_selecionados) > 1:
            st.warning("Selecione apenas um usuário.")
        else:
            linha = usuarios_selecionados.iloc[0].to_dict()
            if usuario_logado_eh_o_mesmo(linha):
                st.warning("Você não pode excluir o próprio usuário logado.")
            else:
                st.session_state.modo_crud_usuario = "excluir"
                st.session_state.usuario_crud_edicao = linha
                st.rerun()

modo = st.session_state.modo_crud_usuario
usuario_edicao = st.session_state.usuario_crud_edicao

if modo in ["novo", "editar"]:
    st.divider()
    st.subheader("➕ Novo Usuário" if modo == "novo" else "✏️ Editar Usuário")

    with st.form("form_crud_usuario"):
        nome = st.text_input(
            "Nome",
            value="" if usuario_edicao is None else str(usuario_edicao["Nome"]),
        )
        usuario = st.text_input(
            "Usuário",
            value="" if usuario_edicao is None else str(usuario_edicao["Usuário"]),
        )

        senha = ""
        if modo == "novo":
            senha = st.text_input("Senha", type="password")

        perfil_novo = st.selectbox(
            "Perfil",
            ["ADMIN", "VENDEDORA", "PROCESSISTA"],
            index=0 if usuario_edicao is None else ["ADMIN", "VENDEDORA", "PROCESSISTA"].index(str(usuario_edicao["Perfil"])),
        )

        ativo = st.selectbox(
            "Status",
            ["Ativo", "Bloqueado"],
            index=0 if usuario_edicao is None or int(usuario_edicao["Ativo"]) == 1 else 1,
        )

        col_salvar, col_cancelar = st.columns(2)
        with col_salvar:
            salvar = st.form_submit_button("💾 Salvar")
        with col_cancelar:
            cancelar = st.form_submit_button("❌ Cancelar")

        if salvar:
            if not nome or not usuario:
                st.warning("Preencha nome e usuário.")
            elif modo == "novo" and not senha:
                st.warning("Preencha a senha.")
            else:
                ativo_num = 1 if ativo == "Ativo" else 0
                try:
                    if modo == "novo":
                        inserir_usuario(nome, usuario, senha, perfil_novo)
                        if ativo_num == 0:
                            usuarios_atualizados = listar_usuarios()
                            id_criado = [u[0] for u in usuarios_atualizados if u[2] == usuario][0]
                            alterar_status_usuario(int(id_criado), 0)
                        st.success("Usuário cadastrado com sucesso.")
                    else:
                        if usuario_logado_eh_o_mesmo(usuario_edicao) and ativo_num == 0:
                            st.warning("Você não pode bloquear o próprio usuário logado.")
                            st.stop()

                        atualizar_usuario(
                            int(usuario_edicao["ID"]),
                            nome,
                            usuario,
                            perfil_novo,
                            ativo_num,
                        )
                        st.success("Usuário atualizado com sucesso.")

                    st.session_state.modo_crud_usuario = None
                    st.session_state.usuario_crud_edicao = None
                    st.rerun()
                except Exception as erro:
                    st.error("Erro ao salvar usuário.")
                    st.exception(erro)

        if cancelar:
            st.session_state.modo_crud_usuario = None
            st.session_state.usuario_crud_edicao = None
            st.rerun()

elif modo == "senha":
    st.divider()
    st.subheader("🔑 Redefinir Senha")
    st.write(f"Usuário selecionado: **{usuario_edicao['Usuário']}**")

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
                alterar_senha_usuario(int(usuario_edicao["ID"]), nova_senha)
                st.success("Senha redefinida com sucesso.")
                st.session_state.modo_crud_usuario = None
                st.session_state.usuario_crud_edicao = None
                st.rerun()

        if cancelar_senha:
            st.session_state.modo_crud_usuario = None
            st.session_state.usuario_crud_edicao = None
            st.rerun()

elif modo == "excluir":
    st.divider()
    st.warning(f"Confirma excluir o usuário {usuario_edicao['Usuário']}?")
    col_confirmar, col_cancelar_exclusao = st.columns(2)

    with col_confirmar:
        if st.button("✅ Confirmar Exclusão"):
            excluir_usuario(int(usuario_edicao["ID"]))
            st.success("Usuário excluído com sucesso.")
            st.session_state.modo_crud_usuario = None
            st.session_state.usuario_crud_edicao = None
            st.rerun()

    with col_cancelar_exclusao:
        if st.button("❌ Cancelar Exclusão"):
            st.session_state.modo_crud_usuario = None
            st.session_state.usuario_crud_edicao = None
            st.rerun()
