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
    items=pricing_items.list_items()
    labels={r[0]:f'{r[0]} — {r[1]}' for r in items}
    codes=list(labels)
    initial=st.session_state.get('pricing_material_code')
    code=st.selectbox('Item KSB da folha',codes,index=codes.index(initial) if initial in codes else None,
                      format_func=lambda x:labels[x],placeholder='Pesquise pelo código ou descrição')
    if not code:st.info('Selecione um item para consultar ou cadastrar sua folha.');return
    st.session_state.pricing_material_code=code
    revisions=repo.revisions(code)
    by_id={r['id']:r for r in revisions}
    rid=st.selectbox('Revisão para consultar ou copiar',[None]+list(by_id),
                    format_func=lambda x:'Nova folha' if x is None else f'Revisão {by_id[x]["number"]} — '+{'DRAFT':'Rascunho','ACTIVE':'Ativa','ARCHIVED':'Arquivada'}[by_id[x]['status']],
                    key=f'pricing_revision_{code}')
    current=by_id.get(rid,{})
    data=current.get('data',{})
    if current:
        c=st.columns(3)
        if c[0].button('Conferir cálculo vigente da revisão'):
            try:_show_calculation(service.preview_sheet(rid,actor)['calculation'])
            except (ValueError,PermissionError) as exc:_error(exc)
        if c[1].button('Publicar revisão / recalcular',disabled='publish' not in permissions or current['status']=='ARCHIVED'):
            try:
                service.activate(rid,actor,version,uuid4().hex);st.success('Preço da folha publicado.');st.rerun()
            except (ValueError,PermissionError) as exc:_error(exc)
        if current['status']=='ACTIVE':
            reason=st.text_input('Motivo para arquivar a folha ativa',key=f'archive_reason_{code}')
            confirm=st.checkbox('Ao arquivar, o item ficará sem preço comercial até nova ativação.',key=f'archive_confirm_{code}')
            if st.button('Arquivar folha ativa',disabled='publish' not in permissions or not confirm or not reason.strip()):
                try:service.archive(code,actor,version,reason,uuid4().hex);st.rerun()
                except (ValueError,PermissionError) as exc:_error(exc)
    catalogs={kind:repo.list_bases(kind) for kind in KINDS}
    lookup={f'{KINDS[k]} | {b["code"]}':(k,b) for k,values in catalogs.items() for b in values}
    reverse={(k,b['id']):label for label,(k,b) in lookup.items()}
    profiles={p['id']:p for p in repo.list_profiles()}
    rows=[]
    for line in data.get('lines',[]):
        rows.append({'Base':reverse.get((line['kind'],line['base_id']),''),'Quantidade':float(line.get('quantity',1)),
          'Consumo':float(line.get('consumption',1)),'Unidade':line.get('unit','UN'),'Modo':line.get('mode','CONSUMO'),
          'Blank C mm':float(line.get('blank_length',0)),'Blank L mm':float(line.get('blank_width',0)),
          'Peça C mm':float(line.get('piece_length',0)),'Peça L mm':float(line.get('piece_width',0)),
          'Horas':float(line.get('hours',0)),'Minutos':float(line.get('minutes',0)),'Pessoas':int(line.get('people',1))})
    if not rows:rows=[dict(Base='',Quantidade=1.0,Consumo=1.0,Unidade='UN',Modo='CONSUMO',**{'Blank C mm':0.,'Blank L mm':0.,'Peça C mm':0.,'Peça L mm':0.,'Horas':0.,'Minutos':0.,'Pessoas':1})]
    st.subheader('Composição de uma peça')
    st.caption('Quantidade e consumo são por peça acabada. Em processos por hora, informe horas/minutos e pessoas. No modo BLANK, use as quatro dimensões. A simulação usa os custos atuais.')
    with st.form(f'sheet_editor_{code}_{rid}'):
        columns=st.columns(3)
        drawing=columns[0].text_input('Código do desenho',value=data.get('drawing_code',''))
        drawing_rev=columns[1].text_input('Revisão do desenho',value=data.get('drawing_revision',''))
        source=columns[2].text_input('Referência da fonte',value=data.get('source',''))
        chosen_profile=st.selectbox('Perfil compartilhado de cálculo',[None]+list(profiles),
          index=([None]+list(profiles)).index(data.get('profile_id')) if data.get('profile_id') in profiles else 0,
          format_func=lambda x:'Parâmetros desta folha' if x is None else profiles[x]['code'])
        cols=st.columns(4)
        margin=cols[0].number_input('Margem bruta (%)',0.,99.9999,float(Decimal(str(data.get('margin','0')))*100),format='%.4f')
        taxes=cols[1].number_input('Impostos de venda (%)',0.,99.9999,float(Decimal(str(data.get('taxes','0')))*100),format='%.4f')
        commission=cols[2].number_input('Comissão / taxa (%)',0.,99.9999,float(Decimal(str(data.get('commission','0')))*100),format='%.4f')
        efficiency=cols[3].number_input('Eficiência (%)',0.0001,100.,float(Decimal(str(data.get('efficiency','1')))*100),format='%.4f')
        if chosen_profile:st.caption('O perfil selecionado fornece eficiência, impostos de venda e arredondamento. Margem e comissão continuam próprias desta folha.')
        cols=st.columns(3)
        rounding=cols[0].selectbox('Arredondamento',list(ROUNDINGS),index=list(ROUNDINGS).index(data.get('rounding','CENT')),format_func=lambda x:ROUNDINGS[x])
        reviewed=cols[1].date_input('Revisão da composição',value=date.fromisoformat(data['reviewed_on']) if data.get('reviewed_on') else today(),max_value=today())
        tool_cost=cols[2].text_input('Amortização de ferramenta por peça (R$)',value=str(data.get('tool_cost','0')))
        basis=st.selectbox('Base comercial do PV',list(BASES),index=list(BASES).index(data.get('basis','')),format_func=lambda x:BASES[x])
        validated=st.checkbox('Conferi esta base de preço com o pedido KSB. O PV com impostos não receberá impostos em duplicidade.',value=data.get('confirmed') is True)
        editor=st.data_editor(pd.DataFrame(rows),num_rows='dynamic',hide_index=True,width='stretch',
          column_config={'Base':st.column_config.SelectboxColumn('Insumo / processo',options=list(lookup)),
                         'Unidade':st.column_config.SelectboxColumn(options=UNITS),
                         'Modo':st.column_config.SelectboxColumn(options=['CONSUMO','BLANK']),
                         'Pessoas':st.column_config.NumberColumn(min_value=1,step=1)})
        note=st.text_area('Observações / justificativa do ferramental',value=data.get('note',''))
        c=st.columns(2)
        simulate=c[0].form_submit_button('Simular composição')
        save=c[1].form_submit_button('Salvar nova revisão em rascunho',disabled='edit' not in permissions)
        if simulate or save:
            lines=[]
            for row in editor.fillna('').to_dict('records'):
                if not row.get('Base'):continue
                kind,base=lookup[row['Base']]
                lines.append(dict(kind=kind,base_id=base['id'],quantity=str(row.get('Quantidade',1)),
                    consumption=str(row.get('Consumo',1)),unit=row.get('Unidade') or base['unit'],mode=row.get('Modo') or 'CONSUMO',
                    blank_length=str(row.get('Blank C mm',0)),blank_width=str(row.get('Blank L mm',0)),
                    piece_length=str(row.get('Peça C mm',0)),piece_width=str(row.get('Peça L mm',0)),
                    hours=str(row.get('Horas') or 0),minutes=str(row.get('Minutos') or 0),people=str(row.get('Pessoas') or 1)))
            params=dict(lines=lines,margin=str(Decimal(str(margin))/100),taxes=str(Decimal(str(taxes))/100),
                        commission=str(Decimal(str(commission))/100),efficiency=str(Decimal(str(efficiency))/100),
                        rounding=rounding,reviewed_on=reviewed.isoformat(),tool_cost=tool_cost,basis=basis,confirmed=validated,
                        drawing_code=drawing,drawing_revision=drawing_rev,source=source,note=note,profile_id=chosen_profile)
            try:
                if simulate:_show_calculation(service.preview_draft(code,params,actor,version)['calculation'])
                if save:
                    created=service.save_draft(code,params,actor,version)
                    st.success(f'Rascunho da revisão {created["number"]} salvo. Selecione-o para conferir e publicar.')
            except (ValueError,PermissionError) as exc:_error(exc)


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
