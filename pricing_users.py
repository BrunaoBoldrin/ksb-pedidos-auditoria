"""User list and permissions within the same edit form."""
import pandas as pd
import streamlit as st
from uuid import uuid4

from pricing_catalog import CatalogService
from pricing_widgets import selected_rows
from ui_components import page_header

PERMISSIONS={'view':'Consultar custos e composição','edit':'Criar revisões em rascunho',
             'publish':'Publicar e arquivar folhas','costs':'Alterar custos base e perfis'}


def render_users(actor):
    page_header('Usuários','Selecione um usuário para editar seus dados e permissões de acesso.')
    service=CatalogService()
    try:users=service.users(actor)
    except PermissionError as exc:st.error(str(exc));return
    by_id={u['id']:u for u in users}
    query=st.text_input('Pesquisar usuário',placeholder='Nome, usuário ou perfil',key='pricing_users_search')
    rows=[{'ID':u['id'],'Nome':u['nome'],'Usuário':u['usuario'],'Perfil':u['perfil'],
           'Status':'Ativo' if u['ativo']==1 else 'Bloqueado'} for u in users]
    table=pd.DataFrame(rows,columns=['ID','Nome','Usuário','Perfil','Status'])
    if query:table=table[table.astype(str).apply(lambda col:col.str.contains(query,case=False,regex=False)).any(axis=1)]
    selection=selected_rows(table,'pricing_users_table')
    chosen=by_id.get(int(selection.iloc[0]['ID'])) if len(selection)==1 else None
    cols=st.columns(5)
    if cols[0].button('➕ Novo Usuário'):
        st.session_state.pricing_user_edit=dict(id=None,version=service.repo.version(),token=uuid4().hex);st.rerun()
    if cols[1].button('✏️ Editar Usuário',disabled=chosen is None):
        st.session_state.pricing_user_edit=dict(id=chosen['id'],version=service.repo.version(),token=uuid4().hex);st.rerun()
    if cols[2].button('🔒 Bloquear/Ativar',disabled=chosen is None):
        try:
            data=dict(name=chosen['nome'],username=chosen['usuario'],profile=chosen['perfil'],active=not bool(chosen['ativo']))
            service.save_user(chosen['id'],data,chosen['permissions'],actor,service.repo.version());st.rerun()
        except (ValueError,PermissionError) as exc:st.error(str(exc))
    if cols[3].button('🔑 Redefinir Senha',disabled=chosen is None):
        st.session_state.pricing_user_action=dict(id=chosen['id'],action='password',version=service.repo.version());st.rerun()
    if cols[4].button('🗑️ Excluir Usuário',disabled=chosen is None):
        st.session_state.pricing_user_action=dict(id=chosen['id'],action='delete',version=service.repo.version());st.rerun()
    edit=st.session_state.get('pricing_user_edit')
    if edit is not None:
        current=by_id.get(edit['id'],{})
        st.subheader('Editar Usuário' if current else 'Novo Usuário')
        identity=str(edit['id'] or 'new')+'_'+edit['token']
        with st.form(f'pricing_user_form_{identity}'):
            c=st.columns(2)
            name=c[0].text_input('Nome',value=current.get('nome',''))
            username=c[1].text_input('Usuário',value=current.get('usuario',''))
            password=st.text_input('Senha',type='password') if not current else None
            profiles=['ADMIN','PROCESSISTA','VENDEDORA']
            c=st.columns(2)
            profile=c[0].selectbox('Perfil',profiles,index=profiles.index(current.get('perfil','VENDEDORA')))
            active=c[1].checkbox('Usuário ativo',value=current.get('ativo',1)==1)
            st.markdown('**Permissões de precificação**')
            st.caption('Administradores têm acesso integral. As permissões abaixo ficam salvas para os demais perfis.')
            permissions=[key for key,label in PERMISSIONS.items() if st.checkbox(label,value=key in current.get('permissions',[]),key=f'user_permission_{identity}_{key}')]
            c=st.columns(2)
            save=c[0].form_submit_button('💾 Salvar usuário e permissões',type='primary')
            cancel=c[1].form_submit_button('Cancelar')
            if save:
                try:
                    service.save_user(edit['id'],dict(name=name,username=username,profile=profile,active=active,password=password),permissions,actor,edit['version'])
                    st.session_state.pop('pricing_user_edit',None);st.session_state.pricing_user_success=True;st.rerun()
                except (ValueError,PermissionError) as exc:st.error(str(exc))
            if cancel:st.session_state.pop('pricing_user_edit',None);st.rerun()
    action=st.session_state.get('pricing_user_action')
    if action:
        current=by_id.get(action['id'])
        if current:
            st.subheader(('Redefinir senha: ' if action['action']=='password' else 'Excluir usuário: ')+current['usuario'])
            with st.form(f'user_action_{action["id"]}_{action["action"]}'):
                if action['action']=='password':
                    password=st.text_input('Nova senha',type='password')
                    repeated=st.text_input('Confirmar nova senha',type='password')
                    confirmed=bool(password) and password==repeated
                else:
                    password=None;confirmed=st.checkbox('Confirmo a exclusão deste usuário')
                c=st.columns(2)
                if c[0].form_submit_button('Confirmar'):
                    if not confirmed:st.error('Confirme a operação e confira os campos.')
                    else:
                        try:
                            service.user_action(action['id'],action['action'],actor,action['version'],password)
                            st.session_state.pop('pricing_user_action',None);st.rerun()
                        except (ValueError,PermissionError) as exc:st.error(str(exc))
                if c[1].form_submit_button('Cancelar operação'):st.session_state.pop('pricing_user_action',None);st.rerun()
    if st.session_state.pop('pricing_user_success',False):st.success('Usuário e permissões salvos.')
