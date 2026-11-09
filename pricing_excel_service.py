"""Preserve and edit imported worksheet inputs without publishing commercial prices."""
import json
import re
from copy import deepcopy
from decimal import Decimal, InvalidOperation

from pricing_calculator import PricingError
from pricing_repository import PricingRepository, json_value, plain
from pricing_service import PricingService, StalePreview


_METADATA = 'id,filename,sha256,linked_codes,version,author,created_at,updated_at'


def normalize_identity(filename, sha256, linked_codes):
    filename = str(filename or '').strip()
    digest = str(sha256 or '').lower()
    if not filename or len(filename) > 255 or not re.fullmatch('[0-9a-f]{64}', digest):
        raise PricingError('Informe o nome da planilha e uma identificação SHA-256 válida.')
    if not isinstance(linked_codes, list) or len(linked_codes) > 1000:
        raise PricingError('Lista de itens vinculados inválida.')
    codes = list(dict.fromkeys(str(code).strip() for code in linked_codes))
    if any(not code or len(code) > 100 for code in codes):
        raise PricingError('Informe códigos de material válidos para os vínculos.')
    return filename, digest, codes


def validate_model(model):
    if not isinstance(model, dict) or model.get('format_version') != 1:
        raise PricingError('Modelo de planilha inválido.')
    cells = model.get('cells')
    outputs = model.get('outputs')
    if not isinstance(cells, dict) or not 1 <= len(cells) <= 5000:
        raise PricingError('A planilha deve conter até 5.000 células.')
    if not isinstance(outputs, dict) or any(not outputs.get(key) for key in ('cost', 'gross', 'pieces')):
        raise PricingError('A planilha precisa identificar custo, preço e quantidade de peças.')
    if any(not isinstance(address, str) or not re.fullmatch('[A-Z]{1,3}[1-9][0-9]{0,5}', address)
           or not isinstance(cell, dict) for address, cell in cells.items()):
        raise PricingError('Células da planilha inválidas.')
    if any(outputs[key] not in cells for key in ('cost', 'gross', 'pieces')):
        raise PricingError('Célula de resultado ausente na planilha.')
    try:
        size = len(json.dumps(model, allow_nan=False, ensure_ascii=False))
    except (TypeError, ValueError):
        raise PricingError('O modelo precisa conter valores válidos para armazenamento.') from None
    if size > 2_000_000:
        raise PricingError('O modelo da planilha excede o limite de armazenamento.')
    return deepcopy(model)


def _validated_inputs(model, edits):
    from pricing_excel import recalculate
    if not isinstance(edits, dict) or len(edits) > len(model['cells']):
        raise PricingError('Alterações da planilha inválidas.')
    try:
        if len(json.dumps(edits, allow_nan=False, ensure_ascii=False)) > 1_000_000:
            raise PricingError('As alterações excedem o limite de armazenamento.')
    except (TypeError, ValueError):
        raise PricingError('Informe valores válidos nas células editadas.') from None
    result = recalculate(model, edits)
    for key in ('cost_total', 'gross_total', 'cost_per_piece', 'gross_per_piece', 'pieces'):
        try:
            value = Decimal(str(result.get(key)))
        except (InvalidOperation, TypeError, ValueError):
            raise PricingError('Corrija as entradas que impedem calcular o custo e o preço da planilha.') from None
        if not value.is_finite() or value < 0 or (key == 'pieces' and value <= 0):
            raise PricingError('O cálculo deve ter valores finitos, não negativos e quantidade de peças positiva.')
    return deepcopy(edits)


class ExcelSourceService:
    def __init__(self, repo=None):
        self.repo = repo or PricingRepository()
        self.pricing = PricingService(self.repo)

    def _require(self, cursor, actor, write=False):
        self.pricing._require(cursor, actor, 'view')
        if write:
            self.pricing._require(cursor, actor, 'edit')
            self.pricing._require(cursor, actor, 'costs')

    def list_sources(self, actor):
        with self.repo.transaction() as cursor:
            self._require(cursor, actor)
            cursor.execute('SELECT ' + _METADATA + ' FROM pricing_excel_sources ORDER BY filename,id')
            return plain(cursor.fetchall())

    def get_source(self, source_id, actor):
        with self.repo.transaction() as cursor:
            self._require(cursor, actor)
            cursor.execute('SELECT * FROM pricing_excel_sources WHERE id=%s', (source_id,))
            row = cursor.fetchone()
            if not row:
                raise PricingError('Planilha importada não encontrada.')
            return plain(row)

    def import_source(self, model, filename, sha256, linked_codes, actor):
        filename, sha256, linked_codes = normalize_identity(filename, sha256, linked_codes)
        model = validate_model(model)
        _validated_inputs(model, {})
        with self.repo.transaction() as cursor:
            self._require(cursor, actor, write=True)
            if linked_codes:
                cursor.execute('SELECT codigo_material FROM materiais WHERE codigo_material=ANY(%s)', (linked_codes,))
                existing = {row['codigo_material'] for row in cursor.fetchall()}
                if existing != set(linked_codes):
                    raise PricingError('Um código KSB vinculado não existe no cadastro de itens.')
            cursor.execute('''INSERT INTO pricing_excel_sources(filename,sha256,model,linked_codes,author)
                VALUES(%s,%s,%s,%s,%s) ON CONFLICT(sha256) DO NOTHING RETURNING *''',
                (filename, sha256, json_value(model), json_value(linked_codes), actor))
            created = cursor.fetchone()
            if created:
                self.pricing._event(cursor, actor, 'PLANILHA EXCEL IMPORTADA', created['id'],
                                    dict(filename=filename, sha256=sha256, linked_codes=linked_codes))
                return plain(created)
            # Reimporting the same file never resets the saved work or source model.
            cursor.execute('SELECT * FROM pricing_excel_sources WHERE sha256=%s', (sha256,))
            return plain(cursor.fetchone())

    def save_inputs(self, source_id, edits, actor, expected_version):
        with self.repo.transaction() as cursor:
            self._require(cursor, actor, write=True)
            cursor.execute('SELECT * FROM pricing_excel_sources WHERE id=%s FOR UPDATE', (source_id,))
            row = cursor.fetchone()
            if not row:
                raise PricingError('Planilha importada não encontrada.')
            if expected_version != row['version']:
                raise StalePreview('Esta planilha foi alterada em outra sessão. Recarregue e confira as alterações.')
            edits = _validated_inputs(row['model'], edits)
            cursor.execute('''UPDATE pricing_excel_sources SET edits=%s,version=version+1,updated_at=now()
                              WHERE id=%s RETURNING *''', (json_value(edits), source_id))
            saved = cursor.fetchone()
            self.pricing._event(cursor, actor, 'PLANILHA EXCEL EDITADA', source_id,
                                dict(before=row['edits'], after=edits, version=saved['version']))
            return plain(saved)
