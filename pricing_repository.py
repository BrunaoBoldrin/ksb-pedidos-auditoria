"""Persistência PostgreSQL da precificação; nunca consulta preços legados como referência."""
import json
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import psycopg2.extras

TABLES={'material':'pricing_materials','component':'pricing_components',
        'process':'pricing_processes','service':'pricing_services'}


def plain(value):
    if isinstance(value, (Decimal,date,datetime)): return str(value)
    if isinstance(value,dict):return {k:plain(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [plain(v) for v in value]
    return value


def json_value(value):
    return psycopg2.extras.Json(plain(value))


class PricingRepository:
    def __init__(self,connect=None):
        if connect is None:
            from database import conectar
            connect=conectar
        self.connect=connect

    @contextmanager
    def transaction(self):
        conn=self.connect()
        try:
            with conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                    yield cursor
        finally:conn.close()

    def migrate(self):
        with self.transaction() as c:
            for migration in sorted((Path(__file__).parent/'migrations').glob('[0-9]*.sql')):
                c.execute(migration.read_text())

    def catalog(self):
        with self.transaction() as c:
            c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            c.execute('SELECT version FROM pricing_control WHERE id=1')
            version=c.fetchone()['version']
            bases={}
            for kind,table in TABLES.items():
                c.execute(f'SELECT * FROM {table} ORDER BY code')
                bases[kind]=plain(c.fetchall())
            c.execute('SELECT * FROM pricing_profiles ORDER BY code')
            return dict(version=version,bases=bases,profiles=plain(c.fetchall()))

    def sheets(self):
        with self.transaction() as c:
            c.execute('''SELECT r.id AS revision_id,r.number,r.status,r.created_at,r.author,
              s.material_code,m.descricao,m.unidade_medida,r.data,
              p.id AS snapshot_id,p.net_price,p.gross_price,p.reviewed_on
              FROM pricing_sheets s JOIN materiais m ON m.codigo_material=s.material_code
              JOIN pricing_revisions r ON r.sheet_id=s.id
              LEFT JOIN LATERAL(SELECT * FROM pricing_prices WHERE revision_id=r.id ORDER BY id DESC LIMIT 1)p ON true
              ORDER BY s.material_code,r.number DESC''')
            return plain(c.fetchall())

    def version(self):
        with self.transaction() as c:
            c.execute('SELECT version FROM pricing_control WHERE id=1')
            return c.fetchone()['version']

    def list_bases(self,kind):
        with self.transaction() as c:
            c.execute(f'SELECT * FROM {TABLES[kind]} ORDER BY code')
            return plain(c.fetchall())

    def list_profiles(self):
        with self.transaction() as c:
            c.execute('SELECT * FROM pricing_profiles ORDER BY code')
            return plain(c.fetchall())

    def revisions(self,code):
        with self.transaction() as c:
            c.execute('''SELECT r.*,s.material_code FROM pricing_revisions r JOIN pricing_sheets s ON s.id=r.sheet_id
                         WHERE s.material_code=%s ORDER BY r.number DESC''',(code,))
            return plain(c.fetchall())

    def snapshot(self,snapshot_id):
        with self.transaction() as c:
            c.execute('SELECT snapshot FROM pricing_prices WHERE id=%s',(snapshot_id,))
            row=c.fetchone()
            return row['snapshot'] if row else None

    def references(self,codes):
        if not codes:return dict(version=self.version(),items={})
        with self.transaction() as c:
            c.execute('''SELECT ctl.version,m.codigo_material,m.unidade_medida,m.ncm,
              r.id AS revision_id,r.number,p.id AS snapshot_id,p.net_price,p.gross_price,
              p.reviewed_on,p.fiscal_context,pub.actor,pub.created_at,
              f.aliquota_icms AS current_icms,f.aliquota_ipi AS current_ipi
              FROM pricing_control ctl CROSS JOIN materiais m
              LEFT JOIN pricing_sheets s ON s.material_code=m.codigo_material
              LEFT JOIN pricing_revisions r ON r.sheet_id=s.id AND r.status='ACTIVE'
              LEFT JOIN LATERAL (SELECT * FROM pricing_prices WHERE revision_id=r.id ORDER BY id DESC LIMIT 1) p ON true
              LEFT JOIN pricing_publications pub ON pub.id=p.publication_id
              LEFT JOIN LATERAL (SELECT aliquota_icms,aliquota_ipi FROM regras_fiscais
                 WHERE regexp_replace(ncm,'[^0-9]','','g')=regexp_replace(m.ncm,'[^0-9]','','g')
                 AND ativo=1 ORDER BY id DESC LIMIT 1) f ON true
              WHERE ctl.id=1 AND m.codigo_material=ANY(%s)''',(list(codes),))
            rows=c.fetchall()
            if rows:version=rows[0]['version']
            else:
                c.execute('SELECT version FROM pricing_control WHERE id=1');version=c.fetchone()['version']
        items={}
        for row in rows:
            state='ACTIVE' if row['snapshot_id'] else ('INVALID' if row['revision_id'] else 'MISSING')
            context=row['fiscal_context'] or {}
            if state=='ACTIVE' and context.get('unit') is not None and str(row['unidade_medida'])!=str(context['unit']):
                state='UNIT_CHANGED'
            if state=='ACTIVE' and context.get('basis')=='GROSS':
                if str(row['ncm'])!=context.get('ncm') or row['current_icms'] is None or Decimal(str(row['current_icms']))!=Decimal(str(context.get('icms'))):
                    state='FISCAL_CHANGED'
            items[row['codigo_material']]=dict(state=state,price=str(row['net_price']) if state=='ACTIVE' else None,
              gross_price=str(row['gross_price']) if state=='ACTIVE' else None,
              snapshot_id=row['snapshot_id'],revision_id=row['revision_id'],revision=row['number'],
              reviewed_on=str(row['reviewed_on']) if row['reviewed_on'] else None,
              published_by=row['actor'],published_at=str(row['created_at']) if row['created_at'] else None,
              unit=context.get('unit',row['unidade_medida']),fiscal_context=context)
        return dict(version=version,items=items)

    def events(self,limit=300):
        with self.transaction() as c:
            c.execute('SELECT * FROM pricing_events ORDER BY id DESC LIMIT %s',(limit,))
            return plain(c.fetchall())
