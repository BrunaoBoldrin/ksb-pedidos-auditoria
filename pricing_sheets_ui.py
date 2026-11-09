"""Process-sheet list and spreadsheet-style per-piece worksheet."""
from copy import deepcopy
from datetime import date,datetime
from decimal import Decimal
from html import escape
from uuid import uuid4
from zoneinfo import ZoneInfo

import json
import pandas as pd
import streamlit as st

import pricing_items
from pricing_catalog import CatalogService
from pricing_sheet_data import COLUMNS,META,TOOL_COLUMNS,base_label,empty_row,sheet_rows,normalize_rows,composition_from_rows,tooling_rows,tooling_from_rows
from pricing_widgets import selected_rows
from pricing_workspace import KINDS
from ui_components import formatar_moeda_brl

ROUNDINGS={'CENT':'Centavos','UP_REAL':'Para cima ao real inteiro'}
STATUSES={'DRAFT':'Rascunho','ACTIVE':'Ativa','ARCHIVED':'Arquivada'}
UNITS=['UN','KG','G','M','MM','M2','BAR','H']


def _today():return datetime.now(ZoneInfo('America/Sao_Paulo')).date()
def _money(value):return formatar_moeda_brl(float(value or 0))


def _open(repo,row,mode,code=None):
    catalog=repo.catalog()
    return dict(row=deepcopy(row or {}),code=code or (row or {}).get('material_code'),mode=mode,
                version=catalog['version'],catalog=catalog,token=uuid4().hex)


def _summary(calculation):
    c=st.columns(4)
    c[0].metric('Custo de uma peça',_money(calculation['cost']))
    c[1].metric('Preço final unitário · sem IPI',_money(calculation['gross_price']))
    c[2].metric('Preço unitário líquido KSB',_money(calculation['net_price']))
    if calculation.get('total_with_ipi') is not None:
        c[3].metric('Preço unitário · com IPI',_money(calculation['total_with_ipi']))
    fiscal=calculation.get('fiscal_context') or {}
    if fiscal.get('source')=='NCM':
        st.caption(f'NCM {fiscal["ncm"]} · ICMS {fiscal["icms"]}% · PIS {fiscal["pis"]}% · COFINS {fiscal["cofins"]}% · IPI {fiscal["ipi"]}%. O líquido KSB é o valor unitário comparado ao pedido.')
    st.caption('Revisão efetiva da composição: '+calculation['reviewed_on'])


def _breakdown(calculation):
    labels={'material':'Matérias-primas','component':'Componentes','process':'Mão de obra com eficiência',
            'service':'Serviços externos','tool':'Ferramental por peça'}
    st.dataframe(pd.DataFrame([{'Composição do custo':label,'Valor por peça':_money(calculation['breakdown'][kind])} for kind,label in labels.items()]),hide_index=True,width='stretch')


def _worksheet_header(opened,data):
    row=opened['row'];revision=row.get('number','Nova')
    title=escape(str(opened['code'] or 'Novo item'))
    description=escape(str(row.get('descricao','')))
    if data.get('import_source_sha256') and st.button('Conferir Excel de origem',key='source_'+opened['token']):
        st.session_state.excel_source_request=data['import_source_sha256']
        st.session_state.pricing_area='Conferência Excel'
        st.rerun()
    st.markdown(f'''<section style="border:1px solid #b9cce9;border-radius:8px;overflow:hidden;margin:18px 0">
      <div style="background:#0b3c7c;color:white;padding:14px 18px;font-weight:700;letter-spacing:.05em">FOLHA DE PROCESSO — 1 PEÇA</div>
      <div style="display:flex;justify-content:space-between;gap:16px;background:#edf3fc;padding:14px 18px;color:#14385e">
      <div><strong>{title}</strong><br>{description}</div><div>Revisão {escape(str(revision))}<br>{STATUSES.get(row.get('status'),'Nova composição')}</div></div></section>''',unsafe_allow_html=True)


def _view(opened,service,permissions):
    row=opened['row'];data=row.get('data',{})
    _worksheet_header(opened,data)
    st.caption(f'Desenho: {data.get("drawing_code") or "—"} · Revisão do desenho: {data.get("drawing_revision") or "—"} · Fonte: {data.get("source") or "—"}')
    st.caption(f'Cliente: {data.get("customer") or "—"} · Vendedor: {data.get("seller") or "—"} · Produto: {data.get("product") or "—"} · Tipo de orçamento: {data.get("quote_type") or "—"}')
    calculation=None
    try:
        if row.get('snapshot_id') and row.get('status')=='ARCHIVED':calculation=service.repo.snapshot(row['snapshot_id'])
        elif row.get('revision_id'):calculation=service.preview_sheet(row['revision_id'],st.session_state.pricing_sheet_actor)['calculation']
    except (ValueError,PermissionError) as exc:st.warning(str(exc))
    if calculation:
        _summary(calculation)
        if row.get('status')=='DRAFT':st.info('Prévia de uma peça. Este preço entra na análise comercial após publicar a revisão.')
        elif row.get('status')=='ACTIVE' and calculation.get('fiscal_context')!=row.get('fiscal_context'):
            st.warning('A regra fiscal mudou desde a publicação. Confira os preços atuais e publique novamente para atualizar a análise comercial.')
    else:st.info('Preço final e líquido KSB pendentes. Corrija a informação indicada acima para concluir o cálculo.')
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
        frame=pd.DataFrame(rows[kind],columns=COLUMNS[kind]).drop(columns=META,errors='ignore')
        if frame.empty:st.caption('Sem linhas nesta composição.');continue
        if calculation:
            evidence=[line for line in calculation['lines'] if line['input']['kind']==kind]
            if len(evidence)==len(frame):
                frame['Fator líquido']=[str(line['base'].get('factor',1)) for line in evidence]
                if kind=='material':frame['Massa (kg/m²)']=[str(line['base'].get('kg_m2') or '') for line in evidence]
                frame['Consumo calculado']=[str(line['amount']) for line in evidence]
                frame['Custo da linha (R$)']=[_money(line['nominal_cost']) for line in evidence]
        st.dataframe(frame,hide_index=True,width='stretch')
    if data.get('tooling'):
        st.markdown('**FERRAMENTAL**')
        st.dataframe(pd.DataFrame(tooling_rows(data),columns=TOOL_COLUMNS),hide_index=True,width='stretch')
        st.caption('A quantidade anual é informativa. O custo total é dividido pela quantidade para amortização.')
    st.markdown('**FORMAÇÃO DO PREÇO**')
    parameters=calculation.get('parameters',{}) if calculation else {}
    values={**data,**parameters}
    c=st.columns(4)
    for col,key,label in zip(c,['margin','taxes','commission','efficiency'],['Margem bruta','Impostos de venda','Comissão / taxa','Eficiência']):
        value='Pendente' if key=='taxes' and not calculation else str((Decimal(str(values.get(key,'1' if key=='efficiency' else '0')))*100).normalize())+'%'
        col.metric(label,value)
    if calculation:_breakdown(calculation)
    if data.get('proposed_prices') and row.get('status')=='DRAFT':
        st.info('Esta revisão propõe alterar custos compartilhados. A publicação atualizará também as outras folhas que usam esses custos.')
    if data.get('note'):st.write(data['note'])


def _edit(opened,service,actor,permissions):
    row=opened['row'];data={**row.get('data',{}),**opened.get('working_fields',{})}
    catalog=opened['catalog']['bases']
    if 'working_rows' not in opened:
        opened['working_rows']=sheet_rows(data,catalog,include_proposals=row.get('status')=='DRAFT')
        opened['grid_epochs']={kind:0 for kind in KINDS}
    _worksheet_header(opened,data)
    price_area=st.container()
    if st.button('Atualizar preços da folha',key='refresh_sheet_'+opened['token']):
        fresh=service.repo.catalog()
        opened['catalog']=fresh;opened['version']=fresh['version'];catalog=fresh['bases']
        for kind in KINDS:
            opened['working_rows'][kind]=normalize_rows(opened['working_rows'][kind],catalog[kind],refresh_prices=True)
            opened['grid_epochs'][kind]+=1
        opened.pop('calculation',None)
        opened.pop('calculation_signature',None)
        st.rerun()
    st.caption('Atualizar preços carrega os valores centrais e descarta propostas de preço desta edição; tempos, consumos e margem são mantidos.')
    key=lambda name:'sheet_'+opened['token']+'_'+name
    cols=st.columns(3)
    drawing=cols[0].text_input('Código do desenho',value=data.get('drawing_code',''),key=key('drawing'))
    drawing_revision=cols[1].text_input('Revisão do desenho',value=data.get('drawing_revision',''),key=key('drawing_revision'))
    source=cols[2].text_input('Referência da fonte',value=data.get('source',''),key=key('source'))
    cols=st.columns(4)
    customer=cols[0].text_input('Cliente',value=data.get('customer',''),key=key('customer'))
    seller=cols[1].text_input('Vendedor',value=data.get('seller',''),key=key('seller'))
    product=cols[2].text_input('Produto da folha',value=data.get('product',''),key=key('product'))
    quote_type=cols[3].text_input('Tipo de orçamento',value=data.get('quote_type',''),key=key('quote_type'),help='Identificação usada na fonte, como integral ou mão de obra.')
    edited={};refresh_needed=False
    for kind,label in KINDS.items():
        st.markdown('**'+label.upper()+'**')
        values=opened['working_rows'][kind] or [empty_row()]
        lookup=[base_label(b) for b in catalog[kind] if b.get('active',True) or any(r.get('Base')==base_label(b) for r in values)]
        config={'Base':st.column_config.SelectboxColumn('Insumo / processo',options=lookup),
                'Unidade':st.column_config.SelectboxColumn('Unidade de consumo',options=UNITS),
                'Modo':st.column_config.SelectboxColumn(options=['CONSUMO','BLANK']),
                'Etapa':st.column_config.SelectboxColumn(options=['Preparação','Execução']),
                'Pessoas':st.column_config.NumberColumn(min_value=1,step=1),
                'Preço (R$)':st.column_config.TextColumn('Preço proposto (R$)',help='Valor compartilhado. Aplicado ao catálogo somente ao publicar a revisão.')}
        config.update({field:None for field in META})
        before=pd.DataFrame(values,columns=COLUMNS[kind]).fillna('')
        frame=st.data_editor(before,key=f'sheet_lines_{opened["token"]}_{kind}_{opened["grid_epochs"][kind]}',
                            num_rows='dynamic',hide_index=True,width='stretch',column_config=config,
                            disabled=META+['Unidade do custo','Custo atual (R$)']+(['Preço (R$)'] if 'costs' not in permissions else []))
        result=normalize_rows(frame.fillna('').to_dict('records'),catalog[kind])
        edited[kind]=result;opened['working_rows'][kind]=deepcopy(result)
        if result!=before.to_dict('records'):
            opened['grid_epochs'][kind]+=1;refresh_needed=True
        by_label={base_label(base):base for base in catalog[kind]}
        for item in result:
            base=by_label.get(item.get('Base'))
            if base and item.get('_proposal_version') not in (None,'') and int(item['_proposal_version'])!=base['version']:
                st.warning('Um preço proposto está vencido. Compare o custo atual e use Atualizar preços da folha antes de propor novo valor.')
                break
    st.markdown('**FERRAMENTAL**')
    if 'working_tooling' not in opened:
        opened['working_tooling']=tooling_rows(data)
        opened['tooling_epoch']=0
    tools_before=pd.DataFrame(opened['working_tooling'],columns=TOOL_COLUMNS).fillna('')
    tools_frame=st.data_editor(tools_before,key=key('tooling')+'_'+str(opened['tooling_epoch']),num_rows='dynamic',hide_index=True,width='stretch',
                               column_config={label:st.column_config.TextColumn(label) for label in TOOL_COLUMNS})
    tools_edited=tools_frame.fillna('').to_dict('records')
    opened['working_tooling']=deepcopy(tools_edited)
    if tools_edited!=tools_before.to_dict('records'):
        opened['tooling_epoch']+=1;refresh_needed=True
    st.caption('Quantidade anual: informação da folha. Quantidade para amortização: número de peças que divide o custo da ferramenta; use 1 para cobrar tudo em uma peça.')
    st.markdown('**FORMAÇÃO DO PREÇO — UMA PEÇA**')
    c=st.columns(4)
    margin=c[0].number_input('Margem bruta (%)',0.,99.9999,float(Decimal(str(data.get('margin','0')))*100),format='%.4f',key=key('margin'))
    tax_area=c[1].empty()
    commission=c[2].number_input('Comissão / taxa (%)',0.,99.9999,float(Decimal(str(data.get('commission','0')))*100),format='%.4f',key=key('commission'))
    efficiency=c[3].number_input('Eficiência (%)',0.0001,100.,float(Decimal(str(data.get('efficiency','1')))*100),format='%.4f',key=key('efficiency'))
    c=st.columns(3)
    has_tooling=any(any(str(value).strip() for value in entry.values()) for entry in tools_edited)
    tool_cost=c[0].text_input('Ferramental por peça (R$)',value=str(data.get('tool_cost','0')),key=key('tool_cost'),disabled=has_tooling,
                              help='Valor direto das folhas anteriores. Quando a tabela de ferramental estiver preenchida, o cálculo usa os custos e quantidades dessa tabela.')
    rounding=c[1].selectbox('Arredondamento',list(ROUNDINGS),index=list(ROUNDINGS).index(data.get('rounding','CENT')),format_func=lambda name:ROUNDINGS[name],key=key('rounding'))
    reviewed=c[2].date_input('Revisão da composição',value=date.fromisoformat(data['reviewed_on']) if data.get('reviewed_on') else _today(),max_value=_today(),key=key('reviewed'))
    note=st.text_area('Observações da folha',value=data.get('note',''),key=key('note'))
    st.caption('Tempos, consumos e margem pertencem à folha. Preços propostos são aplicados aos custos compartilhados somente na publicação.')
    fields=dict(data,margin=str(Decimal(str(margin))/100),commission=str(Decimal(str(commission))/100),
                efficiency=str(Decimal(str(efficiency))/100),tool_cost=tool_cost,rounding=rounding,
                reviewed_on=reviewed.isoformat(),tax_source='NCM',note=note,
                drawing_code=drawing,drawing_revision=drawing_revision,source=source,
                customer=customer,seller=seller,product=product,quote_type=quote_type)
    opened['working_fields']=deepcopy(fields)
    signature=json.dumps(dict(fields=fields,rows=edited,tooling=tools_edited),sort_keys=True)
    if service.repo.version()!=opened['version']:
        fresh=service.repo.catalog()
        for kind in KINDS:
            old_by_id={str(b['id']):b for b in catalog[kind]}
            new_by_id={str(b['id']):b for b in fresh['bases'][kind]}
            for entry in edited[kind]:
                identity=str(entry.get('_base_original',''))
                old=old_by_id.get(identity);new=new_by_id.get(identity)
                if old and new:
                    entry['Base']=base_label(new)
                    # Preserve manual price proposals, including their original version.
                    try:unchanged=Decimal(str(entry.get('Preço (R$)')).replace(',','.'))==Decimal(str(old['price']))
                    except Exception:unchanged=False
                    if unchanged:
                        entry['Preço (R$)']=str(new['price'])
                        entry['_proposal_version']=new['version']
            opened['working_rows'][kind]=normalize_rows(edited[kind],fresh['bases'][kind])
            opened['grid_epochs'][kind]+=1
        opened['catalog']=fresh;opened['version']=fresh['version']
        opened['costs_refreshed']=True
        opened.pop('calculation',None);opened.pop('calculation_signature',None)
        st.rerun()
    c=st.columns(2)
    simulate=c[0].button('Simular composição',key=key('simulate'))
    save=c[1].button('Salvar rascunho',type='primary',disabled='edit' not in permissions,key=key('save'))
    if simulate or save or opened.get('calculation_signature')!=signature:
        try:
            lines,proposed=composition_from_rows(edited,catalog,_today())
            tools=tooling_from_rows(tools_edited)
            fields['tooling']=tools
            opened['working_fields']['tooling']=deepcopy(tools)
            params=dict(fields,lines=lines,proposed_prices=proposed)
            if save:
                result=service.save_draft(opened['code'],params,actor,opened['version'])
                st.session_state.pricing_sheet_pending=dict(id=result['id'],code=opened['code'])
                st.session_state.pricing_sheet_success='Rascunho salvo e selecionado. Confira a composição e publique quando estiver pronta.'
                st.rerun()
            opened['calculation']=service.preview_draft(opened['code'],params,actor,opened['version'])['calculation']
            opened['proposed_count']=len(proposed)
            opened.pop('calculation_error',None)
        except (ValueError,PermissionError) as exc:
            opened.pop('calculation',None);opened['calculation_error']=str(exc)
        opened['calculation_signature']=signature
    if refresh_needed:st.rerun()
    with price_area:
        if opened.pop('costs_refreshed',False):st.info('Custos ou regras fiscais foram atualizados. Confira a nova prévia antes de salvar; seus campos editados foram mantidos.')
        if opened.get('calculation'):
            _summary(opened['calculation'])
            st.caption('Prévia da edição. Salve o rascunho e publique a revisão para usar este preço na análise comercial.')
            if opened.get('proposed_count'):st.info(f'{opened["proposed_count"]} custo(s) compartilhado(s) proposto(s). A publicação recalculará seus dependentes.')
        else:st.warning(opened.get('calculation_error','Preencha a composição para calcular o preço.'))
    taxes=(opened.get('calculation') or {}).get('parameters',{}).get('taxes')
    tax_area.metric('Tributos na formação · NCM',str((Decimal(str(taxes))*100).normalize())+'%' if taxes is not None else 'Pendente')


def render_sheets(actor,service=None,permissions=None):
    service=service or CatalogService();repo=service.repo
    try:permissions=service.permissions(actor) if permissions is None else permissions
    except PermissionError as exc:st.error(str(exc));return
    if 'view' not in permissions:st.error('Você não tem autorização para consultar folhas.');return
    st.session_state.pricing_sheet_actor=actor
    records=repo.sheets();by_id={r['revision_id']:r for r in records}
    query=st.text_input('Pesquisar folha',placeholder='Código KSB, descrição ou desenho',key='pricing_sheet_search')
    rows=[{'ID':r['revision_id'],'Código KSB':r['material_code'],'Descrição':r['descricao'],
           'Revisão':r['number'],'Situação':STATUSES[r['status']],
           'Desenho':r['data'].get('drawing_code',''),'Preço final sem IPI':_money(r.get('gross_price')) if r.get('gross_price') is not None else 'Ver prévia na folha',
           'Líquido KSB':_money(r.get('net_price')) if r.get('net_price') is not None else 'Ver prévia na folha',
           'Revisão dos custos':r.get('reviewed_on') or '—'} for r in records]
    table=pd.DataFrame(rows,columns=['ID','Código KSB','Descrição','Revisão','Situação','Desenho','Preço final sem IPI','Líquido KSB','Revisão dos custos'])
    if query:table=table[table.astype(str).apply(lambda c:c.str.contains(query,case=False,regex=False)).any(axis=1)]
    selected=selected_rows(table,'pricing_sheets_table')
    chosen=by_id.get(int(selected.iloc[0]['ID'])) if len(selected)==1 else None
    c=st.columns(3)
    if c[0].button('Nova folha',disabled='edit' not in permissions):
        st.session_state.pricing_sheet_open=_open(repo,None,'edit')
    if c[1].button('Visualizar folha',disabled=chosen is None):
        st.session_state.pricing_sheet_open=_open(repo,chosen,'view')
    if c[2].button('Editar folha',disabled=chosen is None or 'edit' not in permissions):
        st.session_state.pricing_sheet_open=_open(repo,chosen,'edit')
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
    if opened['mode']=='view' and opened['row'].get('revision_id') in by_id:
        opened['row']=by_id[opened['row']['revision_id']]
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
