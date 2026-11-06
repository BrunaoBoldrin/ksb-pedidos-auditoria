"""Universal costs edited as named fields in cards, with one final save."""
from datetime import date,datetime
from decimal import Decimal
import re
import unicodedata
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from pricing_catalog import CatalogService
from pricing_calculator import number,PricingError
from pricing_workspace import KINDS,ROUNDINGS,new_workspace,workspace_changes,cost_row,profile_row

UNITS=['UN','KG','G','M','MM','M2','BAR','H']
UNIT_LABELS={'UN':'R$/un','KG':'R$/kg','G':'R$/g','M':'R$/m','MM':'R$/mm','M2':'R$/m²','BAR':'R$/barra','H':'R$/h'}


def _today():return datetime.now(ZoneInfo('America/Sao_Paulo')).date()


def _display(value):
    if value in (None,''):return ''
    return format(number(value).normalize(),'f').replace('.',',')


def _initial(snapshot):
    workspace=new_workspace(snapshot)
    for row in workspace['costs']:
        for field in ['Preço (R$)','Fator líquido','kg/m²','Comprimento barra (mm)']:row[field]=_display(row[field])
    for row in workspace['profiles']:
        for field in ['Eficiência (%)','Impostos (%)']:row[field]=_display(row[field])
    workspace['add_nonce']=0
    return workspace


def _capture(state_key,token,collection,row_key,field,widget_key):
    workspace=st.session_state.get(state_key)
    if not workspace or workspace['key']!=token:return
    row=next((r for r in workspace[collection] if r['_key']==row_key),None)
    if row is not None:
        value=st.session_state[widget_key]
        row[field]=value.isoformat() if isinstance(value,date) else value
        workspace.pop('impact',None)


def _input(row,field,label,context,editable,kind='text',options=None,help=None):
    key=f'{context["prefix"]}_{row["_key"]}_{field}'
    callback=dict(on_change=_capture,args=(context['state_key'],context['workspace']['key'],context['collection'],row['_key'],field,key))
    if kind=='checkbox':value=st.checkbox(label,value=bool(row.get(field,False)),key=key,disabled=not editable,help=help,**callback)
    elif kind=='select':
        current=row.get(field);index=options.index(current) if current in options else 0
        value=st.selectbox(label,options,index=index,key=key,disabled=not editable,help=help,**callback)
    elif kind=='date':
        initial=row.get(field) or _today().isoformat()
        initial=initial if isinstance(initial,date) else date.fromisoformat(initial)
        value=st.date_input(label,value=initial,max_value=_today(),key=key,disabled=not editable,**callback).isoformat()
    else:value=st.text_input(label,value=str(row.get(field) or ''),key=key,disabled=not editable,help=help,**callback)
    row[field]=value
    return value


def _usage(row,workspace,profile=False):
    source=workspace['profile_originals' if profile else 'originals'].get(row['_key'])
    return source.get('usage_count') if source is not None else 0


def _remove_option(row,context,editable,profile=False):
    count=_usage(row,context['workspace'],profile)
    if count is None:st.caption('Atualize os valores para conferir os vínculos. A remoção está indisponível.')
    elif count:st.caption(f'Campo vinculado a {count} folha(s). Remoção bloqueada para preservar as precificações.')
    _input(row,'_remove','Remover campo',context,editable and count==0,kind='checkbox')


def _cost_card(title,kind,context,editable):
    workspace=context['workspace']
    with st.container(border=True,height='stretch',key='catalog_card_'+kind):
        st.subheader(title,divider='gray')
        st.caption('Tarifas e valores compartilhados usados nas folhas de processo.')
        rows=[r for r in workspace['costs'] if r['Categoria']==KINDS[kind]]
        if not rows:st.caption('Adicione um campo para cadastrar os valores deste grupo.')
        columns=st.columns(2,gap='medium')
        for index,row in enumerate(rows):
            with columns[index%2]:
                unit=UNIT_LABELS.get(row['Unidade'],'R$/'+row['Unidade'])
                _input(row,'Preço (R$)',f'{row["Descrição"]} ({unit})',context,editable)
                with st.expander('Detalhes · '+row['Código']):
                    _input(row,'Descrição','Nome',context,editable)
                    _input(row,'Código','Código',context,editable)
                    _input(row,'Unidade','Unidade do custo',context,editable,kind='select',options=UNITS)
                    _input(row,'Fator líquido','Fator líquido de compra',context,editable,help='Use 1 para um custo já líquido.')
                    if kind=='material':_input(row,'kg/m²','Massa por área (kg/m²)',context,editable)
                    _input(row,'Comprimento barra (mm)','Comprimento da barra (mm)',context,editable)
                    if kind=='process':_input(row,'Por operador','Tarifa por operador',context,editable,kind='checkbox')
                    _input(row,'Revisão','Data de revisão',context,editable,kind='date')
                    _input(row,'Ativo','Campo ativo',context,editable,kind='checkbox')
                    _input(row,'Observações','Observações',context,editable)
                    _remove_option(row,context,editable)


def _profiles_card(context,editable):
    with st.container(border=True,height='stretch',key='catalog_card_profiles'):
        st.subheader('Padrões comerciais',divider='gray')
        st.caption('Eficiência, tributos e arredondamento dos perfis compartilhados.')
        if not context['workspace']['profiles']:st.caption('Adicione um perfil para definir seus parâmetros.')
        for row in context['workspace']['profiles']:
            st.markdown('**'+row['Perfil']+'**')
            columns=st.columns(2,gap='medium')
            with columns[0]:_input(row,'Eficiência (%)','Eficiência (%)',context,editable)
            with columns[1]:_input(row,'Impostos (%)','Tributos de venda (%)',context,editable)
            _input(row,'Arredondamento','Arredondamento',context,editable,kind='select',options=list(ROUNDINGS.values()))
            with st.expander('Detalhes · '+row['Perfil']):
                _input(row,'Perfil','Nome do perfil',context,editable)
                _input(row,'Revisão','Data de revisão',context,editable,kind='date')
                _input(row,'Ativo','Perfil ativo',context,editable,kind='checkbox')
                _remove_option(row,context,editable,profile=True)


def _add_fields(context,editable,profiles_only):
    workspace=context['workspace'];nonce=workspace['add_nonce']
    with st.expander('Adicionar campos ao formulário',expanded=not workspace['costs'] and not workspace['profiles']):
        if not profiles_only:
            st.markdown('**Novo custo**')
            columns=st.columns(2)
            name=columns[0].text_input('Nome do novo campo',key=f'{context["prefix"]}_new_name_{nonce}',disabled=not editable)
            category=columns[1].selectbox('Categoria do campo',list(KINDS.values()),index=1,key=f'{context["prefix"]}_new_kind_{nonce}',disabled=not editable)
            columns=st.columns(3)
            price=columns[0].text_input('Preço inicial (R$)',key=f'{context["prefix"]}_new_price_{nonce}',disabled=not editable)
            unit=columns[1].selectbox('Unidade do campo',UNITS,key=f'{context["prefix"]}_new_unit_{nonce}',disabled=not editable)
            code=columns[2].text_input('Código opcional',key=f'{context["prefix"]}_new_code_{nonce}',disabled=not editable)
            note=st.text_input('Observação do novo campo',key=f'{context["prefix"]}_new_note_{nonce}',disabled=not editable)
            if st.button('Adicionar campo',disabled=not editable):
                try:
                    code=code.strip() or re.sub(r'[^A-Z0-9]+','-',unicodedata.normalize('NFKD',name).encode('ascii','ignore').decode().upper()).strip('-')[:64]
                    if any(r['Categoria']==category and r['Código'].casefold()==code.casefold() for r in workspace['costs']):raise PricingError('Já existe um campo com esse código neste grupo.')
                    kind=next(k for k,label in KINDS.items() if label==category)
                    base=CatalogService._normalize_base(dict(code=code,description=name,price=price,unit=unit,factor='1',reviewed_on=_today().isoformat(),note=note))
                    base['id']='new_'+uuid4().hex
                    row=cost_row(kind,base);row['Preço (R$)']=_display(base['price'])
                    workspace['costs'].append(row);workspace['add_nonce']+=1;workspace.pop('impact',None)
                    st.rerun()
                except ValueError as exc:st.error(str(exc))
        st.markdown('**Novo perfil**')
        name=st.text_input('Nome do novo perfil',key=f'{context["prefix"]}_new_profile_{nonce}',disabled=not editable)
        if st.button('Adicionar perfil',disabled=not editable):
            if not name.strip():st.error('Informe o nome do perfil.')
            elif any(p['Perfil'].casefold()==name.strip().casefold() for p in workspace['profiles']):st.error('Já existe um perfil com esse nome.')
            else:
                row=profile_row(dict(id='new_'+uuid4().hex,code=name.strip(),data=dict(efficiency='1',taxes='0',rounding='CENT'),reviewed_on=_today().isoformat(),active=True))
                workspace['profiles'].append(row);workspace['add_nonce']+=1;workspace.pop('impact',None);st.rerun()
        st.caption('Adicionar cria o campo nesta edição. O banco só é alterado ao clicar em Salvar alterações.')


def _pending(context):
    workspace=context['workspace'];deletions=list(workspace['deleted'])
    costs=[];profiles=[]
    for collection,target,profile in [('costs',costs,False),('profiles',profiles,True)]:
        originals=workspace['profile_originals' if profile else 'originals']
        for row in workspace[collection]:
            if row.get('_remove'):
                if _usage(row,workspace,profile)!=0:raise PricingError('Campo vinculado não pode ser removido. Atualize o formulário para conferir os vínculos.')
                old=originals.get(row['_key'])
                if old:deletions.append(('profile' if profile else row['_key'].split(':')[0],old['id']))
            else:target.append(row)
    buffer=dict(workspace,deleted=list(dict.fromkeys(deletions)))
    return workspace_changes(buffer,costs,profiles,_today()),costs,profiles


def render_catalog(actor,service=None,profiles_only=False):
    service=service or CatalogService()
    try:permissions=service.permissions(actor)
    except PermissionError as exc:st.error(str(exc));return
    if 'view' not in permissions:st.error('Você não tem autorização para consultar custos.');return
    editable='costs' in permissions;area='profiles' if profiles_only else 'all'
    state_key=f'form_catalog_workspace_{actor}_{area}'
    if state_key not in st.session_state:st.session_state[state_key]=_initial(service.repo.catalog())
    workspace=st.session_state[state_key]
    context=dict(state_key=state_key,workspace=workspace,prefix=f'fc_{actor}_{area}_{workspace["key"]}',collection='costs')
    st.subheader('Perfis de cálculo' if profiles_only else 'Central de custos')
    st.caption('Altere os campos e salve o formulário uma única vez. As folhas dependentes serão atualizadas automaticamente.')
    st.markdown('''<style>
    .st-key-catalog_form_cards [data-testid="stVerticalBlockBorderWrapper"] {background:#fff;border-radius:18px;border-color:#dce6f4;}
    .st-key-catalog_form_cards h3 {font-size:1.15rem;color:#102b50;}
    .st-key-catalog_form_cards [data-baseweb="input"],.st-key-catalog_form_cards [data-baseweb="select"]>div {background:#fff;border-color:#d4dfef;border-radius:8px;}
    </style>''',unsafe_allow_html=True)
    with st.container(key='catalog_form_cards'):
        profile_context=dict(context,collection='profiles')
        if profiles_only:_profiles_card(profile_context,editable)
        else:
            left,right=st.columns(2,gap='medium')
            with left:_cost_card('Custos de produção','process',context,editable)
            with right:_profiles_card(profile_context,editable)
            left,right=st.columns(2,gap='medium')
            with left:_cost_card('Matérias-primas','material',context,editable)
            with right:_cost_card('Componentes','component',context,editable)
            _cost_card('Serviços externos','service',context,editable)
    _add_fields(context,editable,profiles_only)
    st.divider()
    reason=st.text_input('Observações do salvamento',value='Atualização pelo formulário de custos',key=context['prefix']+'_reason',disabled=not editable)
    columns=st.columns(3)
    save=columns[0].button('Salvar alterações',type='primary',disabled=not editable)
    preview=columns[1].button('Ver impacto',disabled=not editable)
    discard=columns[2].button('Recarregar valores salvos')
    if discard:st.session_state.pop(state_key,None);st.rerun()
    if save or preview:
        try:
            (changes,profile_changes,deletions),costs,profiles=_pending(context)
            if not changes and not profile_changes and not deletions:
                if any(r.get('_remove') for r in workspace['costs']+workspace['profiles']):
                    workspace['costs']=costs;workspace['profiles']=profiles;st.rerun()
                st.info('Nenhuma alteração para salvar.')
            elif preview:workspace['impact']=service.preview_catalog(changes,profile_changes,deletions,actor,workspace['version'])['items']
            else:
                result=service.publish_catalog(changes,profile_changes,deletions,actor,workspace['version'],reason,workspace['key'])
                st.session_state.pop(state_key,None);st.session_state[f'form_success_{actor}_{area}']=result['count'];st.rerun()
        except (ValueError,PermissionError) as exc:st.error(str(exc))
    if workspace.get('impact'):
        st.dataframe(pd.DataFrame(workspace['impact']).rename(columns={'code':'Código KSB','before':'Preço anterior','after':'Novo preço','gross':'PV da folha'}),hide_index=True,width='stretch')
    success_key=f'form_success_{actor}_{area}'
    if success_key in st.session_state:st.success(f'Formulário salvo. {st.session_state.pop(success_key)} itens atualizados automaticamente.')
