"""Four shared-cost worksheets, one durable draft and one atomic publication."""
from copy import deepcopy
from datetime import date, datetime
import re
import unicodedata
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from pricing_catalog import CatalogService
from pricing_calculator import number, PricingError
from pricing_workspace import KINDS, COST_COLUMNS, new_workspace, workspace_changes, cost_row

UNITS = ['UN', 'KG', 'G', 'M', 'MM', 'M2', 'BAR', 'H']
TITLES = dict(material='Matérias-primas', component='Componentes', process='Custos de produção', service='Serviços externos')
EDITABLE = set(COST_COLUMNS) - {'_key', 'Categoria'}
NUMERIC = ['Preço (R$)', 'Fator líquido', 'kg/m²', 'Comprimento barra (mm)']


def _today():
    return datetime.now(ZoneInfo('America/Sao_Paulo')).date()


def _display(value):
    return '' if value in (None, '') else format(number(value).normalize(), 'f').replace('.', ',')


def _initial(snapshot):
    workspace = new_workspace(dict(snapshot, profiles=[]))
    for row in workspace['costs']:
        for field in NUMERIC:
            row[field] = _display(row[field])
    workspace['grids'] = {}
    return workspace


def _blank(kind, key=None):
    row = cost_row(kind, dict(id='new_' + uuid4().hex, code='', description='',
                             unit='H' if kind == 'process' else 'KG' if kind == 'material' else 'UN',
                             price='', factor='1', active=True, per_person=True,
                             reviewed_on=_today().isoformat(), note=''))
    if key:
        row['_key'] = key
    return row


def _rows(workspace, kind):
    return [row for row in workspace['costs'] if row['Categoria'] == KINDS[kind]]


def _usage(row, workspace):
    original = workspace['originals'].get(row['_key'])
    return original.get('usage_count') if original is not None else 0


def _cell(value):
    if isinstance(value, date):
        return value.isoformat()
    return '' if value is None else value


def _capture(state_key, token):
    """Apply browser deltas to their immutable baseline, never to edited rows."""
    workspace = st.session_state.get(state_key)
    if not workspace or workspace['key'] != token:
        return
    for kind, grid in workspace['grids'].items():
        delta = st.session_state.get(grid['widget'])
        if delta is None:
            continue
        rows = deepcopy(grid['baseline'])
        for position, values in delta.get('edited_rows', {}).items():
            position = int(position)
            if 0 <= position < len(rows):
                rows[position].update({field: _cell(value) for field, value in values.items() if field in EDITABLE})
        additions = delta.get('added_rows', [])
        while len(grid['added_keys']) < len(additions):
            grid['added_keys'].append(f'{kind}:new_{uuid4().hex}')
        for index, values in enumerate(additions):
            row = _blank(kind, grid['added_keys'][index])
            row.update({field: _cell(value) for field, value in values.items() if field in EDITABLE})
            rows.append(row)
        # Native row deletion is disabled; removal uses the guarded action below.
        if rows != _rows(workspace, kind):
            workspace['costs'] = [row for row in workspace['costs'] if row['Categoria'] != KINDS[kind]] + rows
            workspace.pop('impact', None)


def capture_catalog_draft(actor):
    """Collect deferred cell edits before a button changes the current page."""
    state_key = f'grid_catalog_workspace_{actor}'
    workspace = st.session_state.get(state_key)
    if workspace:
        _capture(state_key, workspace['key'])


def _reset_grid(workspace, kind):
    workspace['grids'].pop(kind, None)
    workspace['epoch'] += 1


def _structure_action(context, kind, remove=False):
    _capture(context['state_key'], context['workspace']['key'])
    workspace = context['workspace']
    if remove:
        selected = [row for row in _rows(workspace, kind) if row['Selecionar']]
        if not selected:
            st.info('Selecione as linhas que deseja remover.')
            return False
        if any(_usage(row, workspace) != 0 for row in selected):
            st.error('Custos vinculados a folhas ou histórico não podem ser removidos. Recarregue os valores se os vínculos estiverem indisponíveis.')
            return False
        keys = {row['_key'] for row in selected}
        for row in selected:
            old = workspace['originals'].get(row['_key'])
            if old:
                workspace['deleted'].append((kind, old['id']))
        workspace['costs'] = [row for row in workspace['costs'] if row['_key'] not in keys]
    else:
        workspace['costs'].append(_blank(kind))
    workspace.pop('impact', None)
    _reset_grid(workspace, kind)
    return True


def _grid(context, kind, editable, technical):
    workspace = context['workspace']
    grid = workspace['grids'].get(kind)
    signature = (editable, _today().isoformat())
    # Navigation and configuration changes reset the editor's internal identity.
    # Capture happened before this point; promote the current draft to its baseline.
    if grid is None or grid['widget'] not in st.session_state or grid.get('signature') != signature:
        workspace['epoch'] += 1
        grid = dict(widget=f'{context["prefix"]}_grid_{kind}_{workspace["epoch"]}',
                    baseline=deepcopy(_rows(workspace, kind)), added_keys=[], signature=signature)
        workspace['grids'][kind] = grid
    rows = deepcopy(grid['baseline'])
    for row in rows:
        count = _usage(row, workspace)
        row['Vínculos'] = 'Verificar vínculos' if count is None else f'{count} folha(s) · protegido' if count else 'Livre'
        row['Revisão'] = date.fromisoformat(row['Revisão']) if row.get('Revisão') else None
    frame = pd.DataFrame(rows, columns=COST_COLUMNS + ['Vínculos'])
    for field in COST_COLUMNS:
        if field in ('Selecionar', 'Por operador', 'Ativo'):
            frame[field] = frame[field].astype(bool)
        elif field != 'Revisão':
            frame[field] = frame[field].astype('string')
    config = {
        '_key': None, 'Categoria': None,
        'Selecionar': st.column_config.CheckboxColumn('Selecionar', width='small', default=False),
        'Código': st.column_config.TextColumn('Código', help='Opcional para novos custos: será sugerido pela descrição.', width='small'),
        'Descrição': st.column_config.TextColumn('Descrição', width='large'),
        'Unidade': st.column_config.SelectboxColumn('Un.', options=UNITS, width='small', default=_blank(kind)['Unidade']),
        'Preço (R$)': st.column_config.TextColumn('Preço (R$)', width='small', help='Preço por unidade de custo. Aceita vírgula decimal e mantém todas as casas informadas.'),
        'Fator líquido': st.column_config.TextColumn('Fator líquido', width='small', default='1', help='De 0 a 1. Use 1 para preço já líquido.'),
        'Revisão': st.column_config.DateColumn('Revisão', format='DD/MM/YYYY', max_value=_today(), default=_today()),
        'Por operador': st.column_config.CheckboxColumn('Por operador', default=True),
        'Ativo': st.column_config.CheckboxColumn('Ativo', default=True),
        'Vínculos': st.column_config.TextColumn('Vínculos', width='medium'),
    }
    columns = ['Selecionar', 'Código', 'Descrição', 'Unidade', 'Preço (R$)', 'Fator líquido']
    if kind == 'process':
        columns.append('Por operador')
    if technical:
        if kind == 'material':
            columns.append('kg/m²')
        columns += ['Comprimento barra (mm)', 'Revisão', 'Ativo', 'Observações']
    columns.append('Vínculos')
    with st.container(border=True, key='catalog_sheet_' + kind):
        st.markdown('**' + TITLES[kind] + '**')
        st.data_editor(frame, key=grid['widget'], num_rows='add' if editable else 'fixed',
                       hide_index=True, width='stretch', height='auto', row_height=38,
                       column_config=config, column_order=columns,
                       disabled=['_key', 'Categoria', 'Vínculos'] if editable else True,
                       on_change='ignore')
        _capture(context['state_key'], workspace['key'])
        selected = [row for row in _rows(workspace, kind) if row['Selecionar']]
        protected = any(_usage(row, workspace) != 0 for row in selected)
        actions = st.columns([1, 1, 2])
        if actions[0].button('+ Linha · ' + TITLES[kind], key=context['prefix'] + '_add_' + kind, disabled=not editable):
            _structure_action(context, kind)
            st.rerun()
        if actions[1].button('Remover selecionados · ' + TITLES[kind], key=context['prefix'] + '_remove_' + kind,
                             disabled=not editable):
            if _structure_action(context, kind, remove=True):
                st.rerun()
        if protected:
            actions[2].caption('Remoção bloqueada: custo vinculado ou vínculos indisponíveis.')
        else:
            actions[2].caption('Novas linhas só serão cadastradas ao salvar tudo.')


def _pending(workspace):
    costs = deepcopy(workspace['costs'])
    seen = set()
    for row in costs:
        new = row['_key'] not in workspace['originals']
        if new and not any(str(row.get(field) or '').strip() for field in ('Código', 'Descrição', 'Preço (R$)')):
            continue
        if new and not str(row.get('Código') or '').strip():
            row['Código'] = re.sub(r'[^A-Z0-9]+', '-', unicodedata.normalize('NFKD', row['Descrição']).encode('ascii', 'ignore').decode().upper()).strip('-')[:64]
        identity = (row['Categoria'], str(row['Código']).strip().casefold())
        if identity in seen:
            raise PricingError(f'{row["Categoria"]}: código repetido {row["Código"]}. Corrija a linha antes de salvar.')
        seen.add(identity)
        try:
            changes, _, _ = workspace_changes(workspace, [row], [], _today())
            for _, data in changes:
                CatalogService._normalize_base(data)
        except ValueError as exc:
            raise PricingError(f'{row["Categoria"]} · {row["Descrição"] or row["Código"] or "Nova linha"}: {exc}') from None
    return workspace_changes(workspace, costs, [], _today())


def render_catalog(actor, service=None, permissions=None):
    service = service or CatalogService()
    try:
        permissions = service.permissions(actor) if permissions is None else permissions
    except PermissionError as exc:
        st.error(str(exc)); return
    if 'view' not in permissions:
        st.error('Você não tem autorização para consultar custos.'); return
    editable = 'costs' in permissions
    state_key = f'grid_catalog_workspace_{actor}'
    if state_key not in st.session_state:
        st.session_state[state_key] = _initial(service.repo.catalog())
    workspace = st.session_state[state_key]
    context = dict(state_key=state_key, workspace=workspace, prefix=f'catalog_{actor}_{workspace["key"]}')
    _capture(state_key, workspace['key'])
    st.subheader('Central de custos')
    st.caption('Preencha as miniplanilhas e salve tudo de uma vez. As folhas dependentes serão recalculadas automaticamente.')
    technical = st.checkbox('Mostrar todos os campos', value=workspace.get('technical', False), key=context['prefix'] + '_technical')
    if technical != workspace.get('technical', False):
        for kind in KINDS:
            _reset_grid(workspace, kind)
    workspace['technical'] = technical
    for kind in KINDS:
        _grid(context, kind, editable, technical)
    st.caption('Tab para avançar · Cole células do Excel · Custos vinculados a folhas ou histórico podem ser editados, mas não excluídos.')
    st.divider()
    reason = st.text_input('Observações do salvamento', value='Atualização pela central de custos',
                           key=context['prefix'] + '_reason', disabled=not editable)
    columns = st.columns(3)
    save = columns[0].button('Salvar tudo', type='primary', disabled=not editable)
    preview = columns[1].button('Ver impacto', disabled=not editable)
    discard = columns[2].button('Recarregar valores salvos', help='Descarta o preenchimento desta edição e carrega o catálogo atual.')
    if discard:
        st.session_state.pop(state_key, None); st.rerun()
    if save or preview:
        _capture(state_key, workspace['key'])
        try:
            changes, _, deletions = _pending(workspace)
            if not changes and not deletions:
                st.info('Nenhuma alteração para salvar.')
            elif preview:
                workspace['impact'] = service.preview_catalog(changes, [], deletions, actor, workspace['version'])['items']
            else:
                result = service.publish_catalog(changes, [], deletions, actor, workspace['version'], reason, workspace['key'])
                st.session_state.pop(state_key, None)
                st.session_state[f'catalog_success_{actor}'] = result['count']
                st.rerun()
        except (ValueError, PermissionError) as exc:
            st.error(str(exc))
            st.caption('Nada foi salvo. Seu preenchimento foi mantido para correção ou conferência.')
    if workspace.get('impact'):
        st.dataframe(pd.DataFrame(workspace['impact']).rename(columns={'code': 'Código KSB', 'before': 'Preço anterior', 'after': 'Novo preço', 'gross': 'PV da folha'}), hide_index=True, width='stretch')
    success_key = f'catalog_success_{actor}'
    if success_key in st.session_state:
        st.success(f'Central de custos salva. {st.session_state.pop(success_key)} itens atualizados automaticamente.')
