"""Editable universal prices with a single transactional save."""
from copy import deepcopy
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from pricing_catalog import CatalogService
from pricing_workspace import (COST_COLUMNS,PROFILE_COLUMNS,KINDS,ROUNDINGS,
                               new_workspace,workspace_changes)

UNITS=['UN','KG','G','M','MM','M2','BAR','H']


def _today():return datetime.now(ZoneInfo('America/Sao_Paulo')).date()


def _stage(workspace,costs,profiles):
    workspace['costs']=deepcopy(costs);workspace['profiles']=deepcopy(profiles)
    workspace['edited_costs']=deepcopy(costs);workspace['edited_profiles']=deepcopy(profiles)
    workspace['epoch']+=1
    workspace.pop('impact',None)
    st.rerun()


def _actions(workspace,costs,profiles,kind,editable):
    rows=costs if kind=='cost' else profiles
    picked=[r for r in rows if r.get('Selecionar')]
    one=picked[0] if len(picked)==1 else None
    cols=st.columns(4)
    suffix='custo' if kind=='cost' else 'perfil'
    if cols[0].button('Novo '+suffix,key=f'new_{kind}',disabled=not editable):
        if kind=='cost':
            rows.append(dict(zip(COST_COLUMNS,[False,'new:'+uuid4().hex,'Componentes','','','UN','','1','','',True,True,_today().isoformat(),''])))
        else:
            rows.append(dict(zip(PROFILE_COLUMNS,[False,'new:'+uuid4().hex,'','100','0','Centavos',True,_today().isoformat()])))
        _stage(workspace,costs,profiles)
    if cols[1].button('Editar selecionado',key=f'edit_{kind}',disabled=not editable or one is None):
        workspace['detail']=dict(kind=kind,key=one['_key'],token=uuid4().hex)
    if cols[2].button('Bloquear / ativar',key=f'toggle_{kind}',disabled=not editable or not picked):
        for row in picked:row['Ativo']=not bool(row['Ativo'])
        _stage(workspace,costs,profiles)
    if cols[3].button('Excluir selecionados',key=f'delete_{kind}',disabled=not editable or not picked):
        keys={r['_key'] for r in picked}
        originals=workspace['originals'] if kind=='cost' else workspace['profile_originals']
        for key in keys:
            if key in originals:
                category='profile' if kind=='profile' else key.split(':')[0]
                workspace['deleted'].append((category,originals[key]['id']))
        rows[:]=[r for r in rows if r['_key'] not in keys]
        _stage(workspace,costs,profiles)
    st.caption('Você pode editar diretamente as células. Excluir e bloquear ficam pendentes até Salvar alterações.')


def _details(workspace,costs,profiles):
    detail=workspace.get('detail')
    if not detail:return
    rows=costs if detail['kind']=='cost' else profiles
    row=next((r for r in rows if r['_key']==detail['key']),None)
    if row is None:workspace.pop('detail',None);return
    st.subheader('Editar custo' if detail['kind']=='cost' else 'Editar perfil')
    with st.form('catalog_detail_'+detail['token']):
        result=dict(row);cols=st.columns(3)
        fields=[c for c in (COST_COLUMNS if detail['kind']=='cost' else PROFILE_COLUMNS) if c not in ('_key','Selecionar')]
        for i,field in enumerate(fields):
            c=cols[i%3]
            if field in ('Ativo','Por operador'):result[field]=c.checkbox(field,value=bool(row[field]))
            elif field in ('Categoria','Unidade','Arredondamento'):
                options=list(KINDS.values()) if field=='Categoria' else UNITS if field=='Unidade' else list(ROUNDINGS.values())
                result[field]=c.selectbox(field,options,index=options.index(row[field]),disabled=field=='Categoria' and not row['_key'].startswith('new:'))
            else:result[field]=c.text_input(field,value=str(row.get(field) or ''))
        c=st.columns(2)
        if c[0].form_submit_button('Aplicar à tabela'):
            rows[rows.index(row)]=result;workspace.pop('detail',None)
            _stage(workspace,costs,profiles)
        if c[1].form_submit_button('Fechar edição'):workspace.pop('detail',None);st.rerun()


def render_catalog(actor,service=None,profiles_only=False):
    service=service or CatalogService()
    try:permissions=service.permissions(actor)
    except PermissionError as exc:st.error(str(exc));return
    if 'view' not in permissions:st.error('Você não tem autorização para consultar custos.');return
    editable='costs' in permissions
    area='profiles' if profiles_only else 'all'
    state_key=f'catalog_workspace_{actor}_{area}'
    if state_key not in st.session_state:st.session_state[state_key]=new_workspace(service.repo.catalog())
    workspace=st.session_state[state_key]
    cost_actions=None
    st.subheader('Perfis de cálculo' if profiles_only else 'Central de custos')
    st.caption('Altere os valores desejados na tabela e salve uma única vez. As folhas ativas relacionadas serão recalculadas automaticamente.')
    if not profiles_only:
        st.markdown('**Matérias-primas, componentes, mão de obra e serviços**')
        cost_key=f'catalog_costs_{actor}_{area}_{workspace["epoch"]}'
        if cost_key not in st.session_state and 'edited_costs' in workspace:
            workspace['costs']=deepcopy(workspace['edited_costs'])
        cost_frame=pd.DataFrame(workspace['costs'],columns=COST_COLUMNS)
        edited=st.data_editor(cost_frame,key=cost_key,hide_index=True,width='stretch',height='auto',
          disabled=['_key'] if editable else True,
          column_config={'_key':None,'Categoria':st.column_config.SelectboxColumn(options=list(KINDS.values())),
                         'Unidade':st.column_config.SelectboxColumn(options=UNITS),
                         'Preço (R$)':st.column_config.TextColumn(help='Custo na unidade de compra; aceita vírgula e preserva a precisão.'),
                         'Fator líquido':st.column_config.TextColumn(help='Use 1 para um custo já líquido.'),
                         'Selecionar':st.column_config.CheckboxColumn(default=False)})
        costs=edited.fillna('').to_dict('records')
        workspace['edited_costs']=deepcopy(costs)
        cost_actions=st.container()
    else:costs=workspace['costs']
    st.markdown('**Parâmetros universais dos perfis**')
    profile_key=f'catalog_profiles_{actor}_{area}_{workspace["epoch"]}'
    if profile_key not in st.session_state and 'edited_profiles' in workspace:
        workspace['profiles']=deepcopy(workspace['edited_profiles'])
    edited=st.data_editor(pd.DataFrame(workspace['profiles'],columns=PROFILE_COLUMNS),key=profile_key,
                          hide_index=True,width='stretch',disabled=['_key'] if editable else True,
                          column_config={'_key':None,'Arredondamento':st.column_config.SelectboxColumn(options=list(ROUNDINGS.values())),
                                         'Selecionar':st.column_config.CheckboxColumn(default=False)})
    profiles=edited.fillna('').to_dict('records')
    workspace['edited_profiles']=deepcopy(profiles)
    if cost_actions is not None:
        with cost_actions:_actions(workspace,costs,profiles,'cost',editable)
    _actions(workspace,costs,profiles,'profile',editable)
    _details(workspace,costs,profiles)
    st.divider()
    try:
        changes,profile_changes,deletions=workspace_changes(workspace,costs,profiles,_today())
        st.caption(f'{len(changes)} custos alterados · {len(profile_changes)} perfis alterados · {len(deletions)} exclusões pendentes')
    except ValueError as exc:
        changes=profile_changes=deletions=[]
        st.warning(str(exc))
    if editable:
        reason=st.text_input('Motivo das alterações',value='Atualização pela central de custos',key=f'catalog_reason_{actor}_{area}')
        cols=st.columns(3)
        save=cols[0].button('Salvar alterações',type='primary',disabled=not (changes or profile_changes or deletions))
        preview=cols[1].button('Ver impacto',disabled=not (changes or profile_changes or deletions))
        discard=cols[2].button('Descartar alterações e atualizar')
        if preview or save:
            try:
                if preview:
                    result=service.preview_catalog(changes,profile_changes,deletions,actor,workspace['version'])
                    workspace['impact']=result['items']
                if save:
                    result=service.publish_catalog(changes,profile_changes,deletions,actor,workspace['version'],reason,workspace['key'])
                    st.session_state.pop(state_key,None)
                    st.session_state[f'catalog_success_{actor}_{area}']=result['count'];st.rerun()
            except (ValueError,PermissionError) as exc:st.error(str(exc))
        if discard:st.session_state.pop(state_key,None);st.rerun()
    if workspace.get('impact'):
        st.markdown('**Impacto nas folhas de processo**')
        st.dataframe(pd.DataFrame(workspace['impact']).rename(columns={'code':'Código KSB','before':'Preço anterior','after':'Novo preço','gross':'PV da folha'}),hide_index=True,width='stretch')
    success_key=f'catalog_success_{actor}_{area}'
    if success_key in st.session_state:
        count=st.session_state.pop(success_key)
        st.success(f'Alterações salvas. {count} itens atualizados automaticamente.')
