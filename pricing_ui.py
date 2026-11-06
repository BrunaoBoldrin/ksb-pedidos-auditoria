"""Telas Streamlit do cadastro técnico e da precificação por peça."""
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

import pricing_items
from pricing_calculator import PricingError
from pricing_repository import PricingRepository
from pricing_service import PricingService
from price_rules import is_price_outdated
from ui_components import dataframe_to_excel_bytes, page_header, formatar_moeda_brl
from ui_rules import format_timestamp_sao_paulo
from pricing_widgets import selected_rows

KINDS={'material':'Matérias-primas','component':'Componentes','process':'Processos internos','service':'Serviços externos'}
UNITS=['UN','KG','G','M','MM','M2','BAR','H']
ROUNDINGS={'UP_REAL':'Para cima ao real inteiro','CENT':'Centavos (arredondamento normal)'}
BASES={'':'Selecione a base do PV','NET':'PV já é o preço líquido do pedido KSB',
       'GROSS':'PV contém ICMS e PIS/COFINS, sem IPI'}


def today():return datetime.now(ZoneInfo('America/Sao_Paulo')).date()
def money(value):return formatar_moeda_brl(float(value or 0))
def decimal_text(value):return str(value if value is not None else '')


def _error(exc):
    st.error(str(exc))


def render_items(actor,can_edit=False,can_view=False):
    page_header('Itens Cadastrados','Identificação e dados técnicos. O preço é formado na folha de processo.')
    rows=pricing_items.list_items()
    frame=pd.DataFrame(rows,columns=pricing_items.COLUMNS).fillna('')
    query=st.text_input('Pesquisar item',placeholder='Código KSB, descrição ou código Glória',key='technical_search')
    selected=frame
    if query:
        selected=frame[frame.astype(str).apply(lambda col:col.str.contains(query,case=False,regex=False)).any(axis=1)]
    st.caption(f'{len(frame)} itens cadastrados. Mostrando até 300 resultados; use a pesquisa para localizar outros.')
    chosen=selected_rows(selected.head(300),'technical_table')
    st.download_button('Baixar cadastro técnico em Excel',dataframe_to_excel_bytes(frame,'Itens'),
                       file_name='itens_cadastrados.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    code=chosen.iloc[0]['Código Material'] if len(chosen)==1 else None
    if len(chosen)>1:st.info('Selecione apenas um item para editar ou abrir a folha.')
    cols=st.columns(3)
    if cols[0].button('Novo item',key='technical_new',disabled=not can_edit):
        st.session_state.technical_values={}
        for field in pricing_items.FIELDS:st.session_state.pop('technical_'+field,None)
        st.rerun()
    if cols[1].button('Editar selecionado',disabled=not can_edit or not code):
        record=frame[frame['Código Material']==code].iloc[0]
        st.session_state.technical_values=dict(zip(pricing_items.FIELDS,record.tolist()))
        for field in pricing_items.FIELDS:st.session_state.pop('technical_'+field,None)
        st.rerun()
    if cols[2].button('Abrir folha de processo',disabled=not code or not can_view):
        st.session_state.pricing_material_code=code
        st.session_state.pricing_sheet_request=code
        st.session_state.pricing_area='Folhas de processo'
        st.session_state.pagina_atual='💰 Precificação'
        st.rerun()
    if 'technical_values' in st.session_state:
        data=st.session_state.technical_values
        with st.form('technical_form'):
            st.subheader('Dados técnicos do item')
            inputs={}
            columns=st.columns(2)
            for i,(field,label) in enumerate(zip(pricing_items.FIELDS,pricing_items.COLUMNS)):
                inputs[field]=columns[i%2].text_input(label,value=str(data.get(field) or ''),key='technical_'+field,
                    disabled=field=='codigo_material' and bool(data.get(field)))
            save=st.form_submit_button('Salvar item',key='technical_save')
            cancel=st.form_submit_button('Cancelar edição')
            if save:
                try:
                    pricing_items.save_item(inputs,actor)
                    st.session_state.pop('technical_values',None);st.success('Item salvo.');st.rerun()
                except (ValueError,PermissionError) as exc:_error(exc)
            if cancel:st.session_state.pop('technical_values',None);st.rerun()
    if can_edit:
        with st.expander('Importar cadastro técnico'):
            st.caption('Planilhas antigas são aceitas. Preços e revisões comerciais serão ignorados.')
            uploaded=st.file_uploader('Planilha de itens',type=['xlsx'],key='technical_import')
            if uploaded:
                imported,notes=pricing_items.import_items(uploaded)
                for note in notes:st.info(note)
                st.dataframe(imported.head(20),hide_index=True,width='stretch')
                if st.button('Importar dados técnicos',disabled=imported.empty):
                    try:
                        for values in imported.itertuples(index=False,name=None):
                            pricing_items.save_item(dict(zip(pricing_items.FIELDS,values)),actor)
                        st.success(f'{len(imported)} itens importados.');st.rerun()
                    except (ValueError,PermissionError) as exc:_error(exc)
        with st.expander('Excluir item sem folha vinculada'):
            confirmed=st.checkbox('Confirmo a exclusão do item selecionado')
            if st.button('Excluir item',disabled=not code or not confirmed):
                try:pricing_items.delete_item(code,actor);st.rerun()
                except (ValueError,PermissionError) as exc:_error(exc)


def _show_calculation(data):
    cols=st.columns(3)
    cols[0].metric('Custo de uma peça',money(data['cost']))
    cols[1].metric('PV da folha',money(data['gross_price']))
    cols[2].metric('Preço líquido comparável KSB',money(data['net_price']))
    labels={'material':'Matéria-prima','component':'Componentes','process':'MDO com eficiência',
            'service':'Serviços externos','tool':'Ferramental'}
    st.dataframe(pd.DataFrame([{'Composição':v,'Custo por peça':money(data['breakdown'][k])} for k,v in labels.items()]),
                 hide_index=True,width='stretch')
    st.caption('Revisão efetiva: '+data['reviewed_on']+'. O cálculo conserva a precisão interna dos custos.')
    with st.expander('Memória da composição'):
        detail=[]
        for row in data['lines']:
            detail.append({'Código':row['base']['code'],'Descrição':row['base']['description'],
                           'Unidade':row['base']['unit'],'Consumo calculado':row['amount'],
                           'Custo antes da eficiência':money(row['nominal_cost'])})
        st.dataframe(pd.DataFrame(detail),hide_index=True,width='stretch')


def _sheet_tab(repo,service,actor,permissions,version):
    from pricing_sheets_ui import render_sheets
    render_sheets(actor,service)


def _costs_tab(repo,service,actor,permissions,version):
    from pricing_catalog import CatalogService
    from pricing_catalog_ui import render_catalog
    render_catalog(actor,CatalogService(repo))


def _profiles_tab(repo,service,actor,permissions,version):
    from pricing_catalog import CatalogService
    from pricing_catalog_ui import render_catalog
    render_catalog(actor,CatalogService(repo),profiles_only=True)


def render_pricing(actor,review_days=90):
    from pricing_catalog import CatalogService
    page_header('Precificação','Folhas por peça e manutenção dos custos compartilhados.')
    service=CatalogService();repo=service.repo
    try:permissions=service.permissions(actor)
    except PermissionError as exc:_error(exc);return
    if 'view' not in permissions:st.error('Você não tem autorização para consultar custos e composição.');return
    area=st.radio('Área de precificação',['Folhas de processo','Central de custos','Perfis de cálculo','Revisões e pendências','Histórico'],horizontal=True,label_visibility='collapsed',key='pricing_area')
    if area=='Folhas de processo':_sheet_tab(repo,service,actor,permissions,repo.version())
    elif area=='Central de custos':_costs_tab(repo,service,actor,permissions,None)
    elif area=='Perfis de cálculo':_profiles_tab(repo,service,actor,permissions,None)
    elif area=='Revisões e pendências':
        items=pricing_items.list_items();refs=repo.references([r[0] for r in items])['items']
        pending=[];active=0
        for row in items:
            ref=refs.get(row[0],{});state=ref.get('state','MISSING')
            if state=='ACTIVE':active+=1
            if state!='ACTIVE' or is_price_outdated(ref.get('reviewed_on'),today(),max_age_days=review_days):
                pending.append({'Código KSB':row[0],'Descrição':row[1],'Situação':'Revisão vencida' if state=='ACTIVE' else {'MISSING':'Sem folha ativa','INVALID':'Cálculo inválido','FISCAL_CHANGED':'Regra fiscal alterada','UNIT_CHANGED':'Unidade do item alterada'}.get(state,state),'Última revisão':ref.get('reviewed_on')})
        c=st.columns(3);c[0].metric('Itens cadastrados',len(items));c[1].metric('Com folha ativa',active);c[2].metric('Pendências',len(pending))
        st.dataframe(pd.DataFrame(pending),hide_index=True,width='stretch')
    else:
        events=repo.events()
        for event in events:event['created_at']=format_timestamp_sao_paulo(event['created_at'])
        st.dataframe(pd.DataFrame(events),hide_index=True,width='stretch')
