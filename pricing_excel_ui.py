"""Editable source-sheet reconciliation, distinct from published commercial prices."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from uuid import uuid4

import pandas as pd
import streamlit as st

from pricing_excel import import_workbook, recalculate
from pricing_widgets import selected_rows
from ui_components import formatar_moeda_brl


def _display(value,kind):
    if value is None:return ''
    if kind=='boolean':return 'Sim' if value else 'Não'
    return str(value).replace('.',',') if kind=='number' else str(value)


def _rows(model,edits):
    sections={}
    for address,cell in model['cells'].items():
        if not cell.get('editable') or cell.get('role')=='layout':continue
        section=cell.get('section') or 'Outros campos'
        if cell.get('role')=='auxiliary':section='Auxiliares · '+section
        sections.setdefault(section,[]).append({'Célula':address,'Campo':cell.get('label') or address,
            'Valor':_display(edits.get(address,cell.get('value')),cell.get('input_type')),
            'Origem':'Referência externa do Excel' if cell.get('external') else 'Entrada da planilha'})
    return sections


def _edits(model,frames,existing=None):
    edits=deepcopy(existing or {})
    for frame in frames:
        for row in frame.fillna('').to_dict('records'):
            address=row['Célula'];cell=model['cells'][address]
            value=str(row['Valor'])
            if value==_display(cell.get('value'),cell.get('input_type')):
                edits.pop(address,None);continue
            if cell.get('input_type')=='boolean':
                if value.strip().lower() not in ('sim','não','nao','true','false','1','0'):
                    raise ValueError(f'{address}: informe Sim ou Não.')
                value=value.strip().lower() in ('sim','true','1')
            edits[address]=value
    return edits


def _money(value):
    return 'Pendente' if value is None else formatar_moeda_brl(value)


def _results(model,original,current):
    columns=st.columns(3)
    columns[0].metric('PV original por peça',_money(original.get('gross_per_piece')))
    columns[1].metric('PV por peça desta edição',_money(current.get('gross_per_piece')))
    columns[2].metric('Custo por peça desta edição',_money(current.get('cost_per_piece')))
    st.caption('Valores da planilha recalculados pelas fórmulas da fonte. A edição desta conferência é salva separadamente do preço comercial do item.')
    labels={'material':'Matérias-primas','component':'Componentes','process':'Mão de obra interna',
            'service':'Serviços externos','tool':'Amortização de ferramental'}
    rows=[]
    for key,label in labels.items():
        if key in original.get('breakdown',{}) or key in current.get('breakdown',{}):
            rows.append({'Resultado da fonte':label,'Original recalculado':_money(original.get('breakdown',{}).get(key)),
                         'Esta edição':_money(current.get('breakdown',{}).get(key))})
    for key,label in [('cost_total','Custo total da fonte'),('gross_total','PV total da fonte'),
                      ('cost_per_piece','Custo por peça'),('gross_per_piece','PV por peça')]:
        rows.append({'Resultado da fonte':label,'Original recalculado':_money(original.get(key)),
                     'Esta edição':_money(current.get(key))})
    st.dataframe(pd.DataFrame(rows),hide_index=True,width='stretch')
    st.caption(f'Quantidade base original: {original.get("pieces") or "pendente"} · Nesta edição: {current.get("pieces") or "pendente"}. Os totais da fonte respeitam o lote e o arredondamento do Excel.')
    # Cached outputs are evidence for reconciliation; they never drive calculations.
    original_values=original.get('values',{})
    differences=[]
    for address in [model['outputs'].get('cost'),model['outputs'].get('gross'),model['outputs'].get('unit_price')]:
        cell=model['cells'].get(address,{})
        cached=cell.get('cached');computed=original_values.get(address)
        if cached is None or computed is None:continue
        try:
            if abs(Decimal(str(cached))-Decimal(str(computed)))>Decimal('0.005'):
                differences.append(f'{address}: Excel armazenado {_money(cached)}; recalculado {_money(computed)}')
        except InvalidOperation:continue
    if differences:
        st.warning('Há diferença entre o resultado armazenado no arquivo e suas fórmulas recalculadas: '+'; '.join(differences))
    for message in dict.fromkeys(current.get('warnings',[])):
        st.warning(str(message))
    errors=current.get('errors',{})
    if errors:
        with st.expander('Células da fonte que precisam de conferência'):
            st.dataframe(pd.DataFrame([{'Célula':cell,'Pendência':str(error)} for cell,error in errors.items()]),hide_index=True,width='stretch')


def _current_prices(source,actor):
    codes=source.get('linked_codes') or []
    if not codes:
        st.info('Esta fonte ainda não possui código KSB vinculado. A conferência dos cálculos está disponível.')
        return
    from pricing_catalog import CatalogService
    service=CatalogService()
    try:
        sheets=service.repo.sheets()
        st.markdown('**Folhas vinculadas · custos atuais e NCM**')
        for code in codes:
            choices=[r for r in sheets if r['material_code']==code and r['status']!='ARCHIVED']
            if not choices:
                st.caption(f'{code}: sem folha disponível.');continue
            row=max(choices,key=lambda r:int(r['number']))
            try:
                calc=service.preview_sheet(row['revision_id'],actor)['calculation']
                st.write(f'{code} · revisão {row["number"]}: PV unitário sem IPI {_money(calc["gross_price"])} · líquido KSB {_money(calc["net_price"])}')
                st.caption('Prévia com custos centrais e regra fiscal do item. '+('Revisão em rascunho.' if row['status']=='DRAFT' else 'Revisão ativa.'))
            except (ValueError,PermissionError) as exc:st.warning(f'{code}: {exc}')
    except (ValueError,PermissionError) as exc:st.warning(str(exc))


def _open(source):
    return dict(source=deepcopy(source),baseline=deepcopy(source.get('edits') or {}),
                draft=deepcopy(source.get('edits') or {}),token=uuid4().hex)


def _editor(workspace,service,actor,editable):
    source=workspace['source'];model=source['model']
    st.subheader(source['filename'])
    st.caption('Preencha as entradas e use Recalcular conferência para comparar. Salvar conferência guarda esta edição e mantém o arquivo original como referência.')
    result_area=st.container()
    frames=[]
    with st.form('excel_form_'+workspace['token']):
        for index,(section,rows) in enumerate(_rows(model,workspace['baseline']).items()):
            area=st.expander(section) if section.startswith('Auxiliares · ') else st.container()
            with area:
                if not section.startswith('Auxiliares · '):st.markdown('**'+section+'**')
                frames.append(st.data_editor(pd.DataFrame(rows),key=f'excel_inputs_{workspace["token"]}_{index}',
                    hide_index=True,width='stretch',num_rows='fixed',height=min(480,38*(len(rows)+1)+3),
                    column_config={'Célula':st.column_config.TextColumn(width='small'),
                        'Campo':st.column_config.TextColumn(width='large'),
                        'Valor':st.column_config.TextColumn(help='Números aceitam vírgula decimal. Datas: AAAA-MM-DD. Campos booleanos: Sim ou Não.'),
                        'Origem':st.column_config.TextColumn(width='medium')},
                    disabled=['Célula','Campo','Origem'] if editable else True))
        a,b=st.columns(2)
        preview=a.form_submit_button('Recalcular conferência',disabled=not editable)
        save=b.form_submit_button('Salvar conferência',type='primary',disabled=not editable)
    if save or preview:
        try:
            workspace['invalid']=True
            candidate=_edits(model,frames,workspace['baseline'])
            result=recalculate(model,candidate)
            workspace['draft']=candidate
            if any(result.get(key) is None for key in ('cost_per_piece','gross_per_piece','pieces')):
                raise ValueError('Há uma entrada inválida que impede o cálculo. Confira as células indicadas.')
            workspace['invalid']=False
            if save:
                updated=service.save_inputs(source['id'],candidate,actor,source['version'])
                st.session_state[f'excel_source_workspace_{actor}']=_open(updated)
                st.session_state[f'excel_source_success_{actor}']=True
                st.rerun()
            else:
                workspace['baseline']=deepcopy(candidate)
                workspace['token']=uuid4().hex
                st.rerun()
        except (ValueError,PermissionError) as exc:
            st.error(str(exc));st.caption('Seu preenchimento foi mantido. Corrija as entradas ou confira a versão salva antes de tentar novamente.')
    with result_area:
        try:
            if workspace.get('invalid'):
                st.info('Corrija as entradas para atualizar os resultados desta edição.')
                st.metric('PV original por peça',_money(recalculate(model).get('gross_per_piece')))
            else:_results(model,recalculate(model),recalculate(model,workspace['draft']))
        except ValueError as exc:st.error(str(exc))
    if st.button('Recarregar conferência salva',key='excel_reload_'+workspace['token']):
        st.session_state[f'excel_source_workspace_{actor}']=_open(service.get_source(source['id'],actor));st.rerun()
    _current_prices(source,actor)


def render_excel_sources(actor,service=None,permissions=None):
    if service is None:
        from pricing_excel_service import ExcelSourceService
        service=ExcelSourceService()
    if permissions is None:
        from pricing_catalog import CatalogService
        permissions=CatalogService().permissions(actor)
    if 'view' not in permissions:
        st.error('Você não tem autorização para consultar as planilhas.');return
    editable={'edit','costs'}.issubset(permissions)
    st.subheader('Conferência Excel')
    st.caption('Planilhas de origem, entradas editáveis e comparação dos resultados por peça.')
    try:sources=service.list_sources(actor)
    except (ValueError,PermissionError) as exc:st.error(str(exc));return
    key=f'excel_source_workspace_{actor}'
    requested=st.session_state.pop('excel_source_request',None)
    if requested:
        found=next((r for r in sources if r['sha256']==requested),None)
        if found:st.session_state[key]=_open(service.get_source(found['id'],actor))
        else:st.warning('A planilha de origem ainda não foi importada para conferência.')
    if sources:
        listing=pd.DataFrame([{'ID':row['id'],'Planilha':row['filename'],'Itens KSB':', '.join(row.get('linked_codes') or []) or 'Vínculo pendente',
                               'Versão':row['version']} for row in sources])
        selected=selected_rows(listing,'excel_sources_table')
        if st.button('Abrir planilha selecionada'):
            if len(selected)!=1:st.info('Selecione uma planilha na lista.')
            else:st.session_state[key]=_open(service.get_source(int(selected.iloc[0]['ID']),actor))
    else:st.info('Nenhuma planilha de origem importada.')
    if editable:
        with st.expander('Importar outra folha Excel'):
            uploaded=st.file_uploader('Folha de processo (.xlsx)',type=['xlsx'],key='excel_source_upload')
            codes=st.text_input('Códigos KSB vinculados, separados por vírgula',key='excel_source_codes')
            if st.button('Importar planilha',disabled=uploaded is None):
                try:
                    raw=uploaded.getvalue();model=import_workbook(raw)
                    row=service.import_source(model,uploaded.name,sha256(raw).hexdigest(),
                        [code.strip() for code in codes.split(',') if code.strip()],actor)
                    st.session_state[key]=_open(row);st.rerun()
                except (ValueError,PermissionError) as exc:st.error(str(exc))
    if st.session_state.pop(f'excel_source_success_{actor}',False):st.success('Conferência salva.')
    if key in st.session_state:_editor(st.session_state[key],service,actor,editable)
