"""Process-sheet list and spreadsheet-style per-piece worksheet."""
from copy import deepcopy
from datetime import date,datetime
from decimal import Decimal
from html import escape
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

import pricing_items
from pricing_catalog import CatalogService
from pricing_sheet_data import COLUMNS,base_label,empty_row,sheet_rows,composition_from_rows
from pricing_widgets import selected_rows
from pricing_workspace import KINDS
from ui_components import formatar_moeda_brl

ROUNDINGS={'CENT':'Centavos','UP_REAL':'Para cima ao real inteiro'}
BASES={'':'Selecione a base do PV','NET':'PV já é o preço líquido do pedido KSB',
       'GROSS':'PV contém ICMS e PIS/COFINS, sem IPI'}
STATUSES={'DRAFT':'Rascunho','ACTIVE':'Ativa','ARCHIVED':'Arquivada'}
UNITS=['UN','KG','G','M','MM','M2','BAR','H']


def _today():return datetime.now(ZoneInfo('America/Sao_Paulo')).date()
def _money(value):return formatar_moeda_brl(float(value or 0))


def _open(repo,row,mode,code=None):
    catalog=repo.catalog()
    return dict(row=deepcopy(row or {}),code=code or (row or {}).get('material_code'),mode=mode,
                version=catalog['version'],catalog=catalog,token=uuid4().hex)


def _summary(calculation):
    c=st.columns(3)
    c[0].metric('Custo de uma peça',_money(calculation['cost']))
    c[1].metric('PV da folha',_money(calculation['gross_price']))
    c[2].metric('Preço líquido comparável KSB',_money(calculation['net_price']))
    labels={'material':'Matérias-primas','component':'Componentes','process':'Mão de obra com eficiência',
            'service':'Serviços externos','tool':'Ferramental por peça'}
    st.dataframe(pd.DataFrame([{'Composição do custo':label,'Valor por peça':_money(calculation['breakdown'][kind])} for kind,label in labels.items()]),hide_index=True,width='stretch')
    st.caption('Revisão efetiva da composição: '+calculation['reviewed_on'])


def _worksheet_header(opened,data):
    row=opened['row'];revision=row.get('number','Nova')
    title=escape(str(opened['code'] or 'Novo item'))
    description=escape(str(row.get('descricao','')))
    st.markdown(f'''<section style="border:1px solid #b9cce9;border-radius:8px;overflow:hidden;margin:18px 0">
      <div style="background:#0b3c7c;color:white;padding:14px 18px;font-weight:700;letter-spacing:.05em">FOLHA DE PROCESSO — 1 PEÇA</div>
      <div style="display:flex;justify-content:space-between;gap:16px;background:#edf3fc;padding:14px 18px;color:#14385e">
      <div><strong>{title}</strong><br>{description}</div><div>Revisão {escape(str(revision))}<br>{STATUSES.get(row.get('status'),'Nova composição')}</div></div></section>''',unsafe_allow_html=True)


def _view(opened,service,permissions):
    row=opened['row'];data=row.get('data',{})
    _worksheet_header(opened,data)
    st.caption(f'Desenho: {data.get("drawing_code") or "—"} · Revisão do desenho: {data.get("drawing_revision") or "—"} · Fonte: {data.get("source") or "—"}')
    calculation=None
    try:
        if row.get('snapshot_id'):calculation=service.repo.snapshot(row['snapshot_id'])
        elif row.get('revision_id'):calculation=service.preview_sheet(row['revision_id'],st.session_state.pricing_sheet_actor)['calculation']
    except (ValueError,PermissionError) as exc:st.warning(str(exc))
    catalog=opened['catalog']['bases']
    if calculation and calculation['lines']:
        catalog={kind:[] for kind in KINDS}
        for line in calculation['lines']:
            kind=line['input']['kind'];base=line['base']
            if not any(b['id']==base['id'] for b in catalog[kind]):catalog[kind].append(base)
    try:rows=sheet_rows(data,catalog,include_proposals=row.get('status')=='DRAFT')
    except ValueError as exc:st.error(str(exc));rows={kind:[] for kind in KINDS}
    for kind,label in KINDS.items():
        st.markdown('**'+label.upper()+'**')
        frame=pd.DataFrame(rows[kind],columns=COLUMNS[kind])
        if frame.empty:st.caption('Sem linhas nesta composição.');continue
        if calculation:
            evidence=[line for line in calculation['lines'] if line['input']['kind']==kind]
            if len(evidence)==len(frame):
                frame['Fator líquido']=[str(line['base'].get('factor',1)) for line in evidence]
                if kind=='material':frame['Massa (kg/m²)']=[str(line['base'].get('kg_m2') or '') for line in evidence]
                frame['Consumo calculado']=[str(line['amount']) for line in evidence]
                frame['Custo da linha (R$)']=[_money(line['nominal_cost']) for line in evidence]
        st.dataframe(frame,hide_index=True,width='stretch')
    st.markdown('**FORMAÇÃO DO PREÇO**')
    parameters=calculation.get('parameters',{}) if calculation else {}
    values={**data,**parameters}
    c=st.columns(4)
    for col,key,label in zip(c,['margin','taxes','commission','efficiency'],['Margem bruta','Impostos de venda','Comissão / taxa','Eficiência']):
        col.metric(label,str((Decimal(str(values.get(key,'1' if key=='efficiency' else '0')))*100).normalize())+'%')
    if calculation:_summary(calculation)
    if data.get('proposed_prices') and row.get('status')=='DRAFT':
        st.info('Esta revisão propõe alterar custos compartilhados. A publicação atualizará também as outras folhas que usam esses custos.')
    if data.get('note'):st.write(data['note'])


def _edit(opened,service,actor,permissions):
    row=opened['row'];data=row.get('data',{});catalog=opened['catalog']['bases']
    _worksheet_header(opened,data)
    profiles={p['id']:p for p in opened['catalog']['profiles'] if p.get('active',True) or p['id']==data.get('profile_id')}
    options=[None]+list(profiles)
    initial=data.get('profile_id') if data.get('profile_id') in profiles else None
    profile_id=st.selectbox('Perfil compartilhado de cálculo',options,index=options.index(initial),
                           format_func=lambda p:'Parâmetros desta folha' if p is None else profiles[p]['code'],key='sheet_profile_'+opened['token'])
    effective={**data,**(profiles[profile_id]['data'] if profile_id is not None else {})}
    if profile_id is not None:st.caption('Eficiência, impostos e arredondamento vêm do perfil. Para editá-los somente nesta folha, selecione Parâmetros desta folha.')
    rows=sheet_rows(data,catalog,include_proposals=row.get('status')=='DRAFT')
    with st.form('sheet_form_'+opened['token']+'_'+str(profile_id)):
        cols=st.columns(3)
        drawing=cols[0].text_input('Código do desenho',value=data.get('drawing_code',''))
        drawing_revision=cols[1].text_input('Revisão do desenho',value=data.get('drawing_revision',''))
        source=cols[2].text_input('Referência da fonte',value=data.get('source',''))
        edited={}
        for kind,label in KINDS.items():
            st.markdown('**'+label.upper()+'**')
            values=rows[kind] or [empty_row()]
            lookup=[base_label(b) for b in catalog[kind] if b.get('active',True) or any(r.get('Base')==base_label(b) for r in values)]
            config={'Base':st.column_config.SelectboxColumn('Insumo / processo',options=lookup),
                    'Unidade':st.column_config.SelectboxColumn(options=UNITS),
                    'Modo':st.column_config.SelectboxColumn(options=['CONSUMO','BLANK']),
                    'Etapa':st.column_config.SelectboxColumn(options=['Preparação','Execução']),
                    'Pessoas':st.column_config.NumberColumn(min_value=1,step=1),
                    'Preço (R$)':st.column_config.TextColumn('Preço base (R$)',help='Valor compartilhado. Alterar será aplicado ao catálogo ao publicar esta revisão.')}
            frame=st.data_editor(pd.DataFrame(values,columns=COLUMNS[kind]),key=f'sheet_lines_{opened["token"]}_{kind}_{profile_id}',
                                 num_rows='dynamic',hide_index=True,width='stretch',column_config=config,
                                 disabled=['Preço (R$)'] if 'costs' not in permissions else [])
            edited[kind]=frame.fillna('').to_dict('records')
        st.markdown('**FORMAÇÃO DO PREÇO — UMA PEÇA**')
        c=st.columns(4)
        margin=c[0].number_input('Margem bruta (%)',0.,99.9999,float(Decimal(str(data.get('margin','0')))*100),format='%.4f')
        taxes=c[1].number_input('Impostos de venda (%)',0.,99.9999,float(Decimal(str(effective.get('taxes','0')))*100),format='%.4f',disabled=profile_id is not None)
        commission=c[2].number_input('Comissão / taxa (%)',0.,99.9999,float(Decimal(str(data.get('commission','0')))*100),format='%.4f')
        efficiency=c[3].number_input('Eficiência (%)',0.0001,100.,float(Decimal(str(effective.get('efficiency','1')))*100),format='%.4f',disabled=profile_id is not None)
        c=st.columns(3)
        tool_cost=c[0].text_input('Ferramental por peça (R$)',value=str(data.get('tool_cost','0')))
        rounding=c[1].selectbox('Arredondamento',list(ROUNDINGS),index=list(ROUNDINGS).index(effective.get('rounding','CENT')),format_func=lambda key:ROUNDINGS[key],disabled=profile_id is not None)
        reviewed=c[2].date_input('Revisão da composição',value=date.fromisoformat(data['reviewed_on']) if data.get('reviewed_on') else _today(),max_value=_today())
        basis=st.selectbox('Base comercial do PV',list(BASES),index=list(BASES).index(data.get('basis','')),format_func=lambda key:BASES[key])
        confirmed=st.checkbox('Conferi esta base comercial com o pedido KSB.',value=data.get('confirmed') is True)
        note=st.text_area('Observações da folha',value=data.get('note',''))
        st.caption('Tempos, consumos e margem pertencem à folha. Preços editados são propostas de custos compartilhados, aplicadas somente na publicação da revisão.')
        c=st.columns(2)
        simulate=c[0].form_submit_button('Simular composição')
        save=c[1].form_submit_button('Salvar rascunho',type='primary',disabled='edit' not in permissions)
        if simulate or save:
            try:
                lines,proposed=composition_from_rows(edited,catalog,_today())
                params=dict(lines=lines,proposed_prices=proposed,profile_id=profile_id,
                            margin=str(Decimal(str(margin))/100),taxes=str(Decimal(str(taxes))/100),commission=str(Decimal(str(commission))/100),
                            efficiency=str(Decimal(str(efficiency))/100),tool_cost=tool_cost,rounding=rounding,
                            reviewed_on=reviewed.isoformat(),basis=basis,confirmed=confirmed,note=note,
                            drawing_code=drawing,drawing_revision=drawing_revision,source=source)
                if simulate:
                    _summary(service.preview_draft(opened['code'],params,actor,opened['version'])['calculation'])
                    if proposed:st.info(f'{len(proposed)} custo(s) compartilhado(s) proposto(s). A publicação recalculará seus dependentes.')
                if save:
                    result=service.save_draft(opened['code'],params,actor,opened['version'])
                    st.session_state.pricing_sheet_pending=dict(id=result['id'],code=opened['code'])
                    st.session_state.pricing_sheet_success='Rascunho salvo e selecionado. Confira a composição e publique quando estiver pronta.'
                    st.rerun()
            except (ValueError,PermissionError) as exc:st.error(str(exc))


def render_sheets(actor,service=None):
    service=service or CatalogService();repo=service.repo
    try:permissions=service.permissions(actor)
    except PermissionError as exc:st.error(str(exc));return
    if 'view' not in permissions:st.error('Você não tem autorização para consultar folhas.');return
    st.session_state.pricing_sheet_actor=actor
    records=repo.sheets();by_id={r['revision_id']:r for r in records}
    query=st.text_input('Pesquisar folha',placeholder='Código KSB, descrição ou desenho',key='pricing_sheet_search')
    rows=[{'ID':r['revision_id'],'Código KSB':r['material_code'],'Descrição':r['descricao'],
           'Revisão':r['number'],'Situação':STATUSES[r['status']],
           'Desenho':r['data'].get('drawing_code',''),'PV da folha':_money(r.get('gross_price')) if r.get('gross_price') is not None else 'Não publicado',
           'Revisão dos custos':r.get('reviewed_on') or '—'} for r in records]
    table=pd.DataFrame(rows,columns=['ID','Código KSB','Descrição','Revisão','Situação','Desenho','PV da folha','Revisão dos custos'])
    if query:table=table[table.astype(str).apply(lambda c:c.str.contains(query,case=False,regex=False)).any(axis=1)]
    selected=selected_rows(table,'pricing_sheets_table')
    chosen=by_id.get(int(selected.iloc[0]['ID'])) if len(selected)==1 else None
    c=st.columns(3)
    if c[0].button('Nova folha',disabled='edit' not in permissions):
        st.session_state.pricing_sheet_open=_open(repo,None,'edit');st.rerun()
    if c[1].button('Visualizar folha',disabled=chosen is None):
        st.session_state.pricing_sheet_open=_open(repo,chosen,'view');st.rerun()
    if c[2].button('Editar folha',disabled=chosen is None or 'edit' not in permissions):
        st.session_state.pricing_sheet_open=_open(repo,chosen,'edit');st.rerun()
    pending=st.session_state.pop('pricing_sheet_pending',None)
    requested=st.session_state.pop('pricing_sheet_request',None)
    if pending:
        row=by_id.get(pending['id'])
        if row:st.session_state.pricing_sheet_open=_open(repo,row,'view')
    elif requested:
        row=next((r for r in records if r['material_code']==requested and r['status']=='ACTIVE'),None) or next((r for r in records if r['material_code']==requested),None)
        st.session_state.pricing_sheet_open=_open(repo,row,'view' if row else 'edit',requested)
    opened=st.session_state.get('pricing_sheet_open')
    if not opened:
        st.info('Selecione uma folha na tabela para visualizar ou editar, ou crie uma nova folha.');return
    if opened.get('actor',actor)!=actor:
        st.session_state.pop('pricing_sheet_open',None);return
    opened['actor']=actor
    if not opened['code']:
        items=pricing_items.list_items();labels={r[0]:f'{r[0]} — {r[1]}' for r in items}
        code=st.selectbox('Item KSB da folha',list(labels),index=None,format_func=lambda key:labels[key],placeholder='Selecione o item para a nova folha')
        if not code:return
        opened['code']=code;opened['row']['descricao']=next(r[1] for r in items if r[0]==code)
    if st.session_state.get('pricing_sheet_success'):st.success(st.session_state.pop('pricing_sheet_success'))
    if opened['mode']=='edit':_edit(opened,service,actor,permissions)
    else:
        _view(opened,service,permissions)
        row=opened['row']
        if row.get('revision_id') and row['status']!='ARCHIVED':
            if st.button('Publicar revisão',type='primary',disabled='publish' not in permissions):
                try:
                    result=service.activate(row['revision_id'],actor,opened['version'],uuid4().hex)
                    st.session_state.pricing_sheet_success=f'Revisão publicada. {result["count"]} itens atualizados.'
                    st.session_state.pricing_sheet_pending=dict(id=row['revision_id'],code=opened['code']);st.rerun()
                except (ValueError,PermissionError) as exc:st.error(str(exc))
        if row.get('status')=='ACTIVE' and 'publish' in permissions:
            with st.expander('Arquivar folha ativa'):
                reason=st.text_input('Motivo do arquivamento',key='archive_reason_'+opened['token'])
                confirmed=st.checkbox('Confirmo que o item ficará sem preço vigente até nova publicação.',key='archive_confirm_'+opened['token'])
                if st.button('Arquivar folha',disabled=not reason.strip() or not confirmed):
                    try:
                        service.archive(opened['code'],actor,opened['version'],reason,uuid4().hex)
                        st.session_state.pop('pricing_sheet_open',None);st.rerun()
                    except (ValueError,PermissionError) as exc:st.error(str(exc))
    if st.button('Fechar folha'):
        st.session_state.pop('pricing_sheet_open',None);st.rerun()
