"""Integration tests use a private PostgreSQL schema, never shared application tables."""
import os
import unittest
import uuid
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import psycopg2
from psycopg2 import sql

from pricing_service import PricingService, StalePreview
from pricing_repository import PricingRepository
from pricing_calculator import PricingError


@unittest.skipUnless(os.environ.get('PRICING_TEST_DSN'), 'PostgreSQL de teste não configurado')
class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.dsn=os.environ['PRICING_TEST_DSN']
        self.schema='pricing_it_'+uuid.uuid4().hex
        conn=psycopg2.connect(self.dsn)
        with conn,conn.cursor() as c:
            c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(self.schema)))
        conn.close()
        def connect():
            return psycopg2.connect(self.dsn,options=f'-c search_path={self.schema}')
        self.connect=connect
        conn=connect()
        with conn,conn.cursor() as c:
            c.execute('CREATE TABLE usuarios(id serial primary key,usuario text unique,nome text,perfil text,ativo int)')
            c.execute("INSERT INTO usuarios(usuario,nome,perfil,ativo) VALUES ('admin','Administrador','ADMIN',1),('venda','Vendas','VENDEDORA',1)")
            c.execute('CREATE TABLE materiais(codigo_material text primary key,descricao text,material text,norma text,codigo_interno_jundiai text,codigo_interno_varzea text,ncm text,unidade_medida text,preco_revisado float,data_ultima_revisao text,usuario_ultima_revisao_preco text)')
            c.execute("INSERT INTO materiais(codigo_material,descricao,ncm,unidade_medida,preco_revisado) VALUES ('A','Teste A','123','UN',999),('B','Teste B','123','UN',999),('C','Teste C','123','UN',999)")
            c.execute('CREATE TABLE revisoes_preco(id serial primary key,codigo_material text,descricao_material text,preco_anterior numeric,preco_novo numeric,usuario text,origem text,criado_em timestamptz default now())')
            c.execute('CREATE TABLE regras_fiscais(id serial,ncm text,aliquota_icms float,aliquota_ipi float,observacao text,ativo int)')
            c.execute("INSERT INTO regras_fiscais VALUES(1,'123',18,0,'teste',1)")
        conn.close()
        self.repo=PricingRepository(connect)
        self.repo.migrate()
        self.service=PricingService(self.repo)
        self.base=self.service.save_base('component',dict(code='COMP',description='Componente',price='100',unit='UN',factor='1',reviewed_on='2026-11-06',active=True),actor='admin',expected_version=0,key=uuid.uuid4().hex)

    def tearDown(self):
        conn=psycopg2.connect(self.dsn)
        with conn,conn.cursor() as c:
            c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
        conn.close()

    def data(self,**changes):
        d=dict(lines=[dict(kind='component',base_id=self.base['id'],quantity='1',consumption='1',unit='UN')],
               margin='0.2',taxes='0.3',commission='0',efficiency='1',rounding='CENT',
               reviewed_on='2026-11-06',confirmed=True,basis='NET',tool_cost='0')
        d.update(changes)
        return d

    def activate(self,code='A',**changes):
        rev=self.service.save_draft(code,self.data(**changes),'admin',self.repo.version())
        self.service.activate(rev['id'],'admin',self.repo.version(),uuid.uuid4().hex)
        return rev

    def test_migration_is_repeatable_and_no_manual_price_fallback(self):
        self.repo.migrate()
        refs=self.repo.references(['A','B'])
        self.assertIsNone(refs['items']['A']['price'])
        self.assertEqual(refs['items']['A']['state'],'MISSING')

    def test_shared_cost_updates_only_dependents_and_preserves_snapshot(self):
        self.activate('A');self.activate('B')
        old=self.repo.references(['A'])['items']['A']
        data=self.repo.list_bases('component')[0];data['price']='110'
        preview=self.service.preview_costs([('component',data)],'admin')
        self.assertEqual(len(preview['items']),2)
        result=self.service.publish_costs([('component',data)],'admin',preview['version'],'motivo','unique-update')
        self.assertEqual(result['count'],2)
        refs=self.repo.references(['A','B','C'])['items']
        self.assertEqual(refs['A']['price'],'220.00')
        self.assertEqual(refs['B']['price'],'220.00')
        self.assertIsNone(refs['C']['price'])
        self.assertEqual(self.repo.snapshot(old['snapshot_id'])['net_price'],'200.00')
        again=self.service.publish_costs([('component',data)],'admin',preview['version'],'motivo','unique-update')
        self.assertEqual(again['publication_id'],result['publication_id'])

    def test_draft_does_not_change_price_and_activation_archives_previous(self):
        self.activate()
        rev=self.service.save_draft('A',self.data(margin='0'),'admin',self.repo.version())
        self.assertEqual(self.repo.references(['A'])['items']['A']['price'],'200.00')
        self.service.activate(rev['id'],'admin',self.repo.version(),uuid.uuid4().hex)
        self.assertEqual(self.repo.references(['A'])['items']['A']['price'],'142.86')
        self.service.archive('A','admin',self.repo.version(),'Arquivar',uuid.uuid4().hex)
        self.assertIsNone(self.repo.references(['A'])['items']['A']['price'])

    def test_invalid_dependency_rolls_back_all_base_changes(self):
        self.activate()
        data=self.repo.list_bases('component')[0];data['active']=False
        version=self.repo.version()
        with self.assertRaises(PricingError):
            self.service.publish_costs([('component',data)],'admin',version,'teste',uuid.uuid4().hex)
        self.assertTrue(self.repo.list_bases('component')[0]['active'])
        self.assertEqual(self.repo.version(),version)
        self.assertEqual(self.repo.references(['A'])['items']['A']['price'],'200.00')

    def test_stale_preview_is_rejected_even_for_different_cost_change(self):
        version=self.repo.version()
        self.service.save_draft('A',self.data(),'admin',version)
        with self.assertRaises(StalePreview):
            self.service.save_draft('B',self.data(),'admin',version)

    def test_permission_revocation_and_inactive_user_apply_immediately(self):
        with self.assertRaises(PermissionError):self.service.preview_costs([],'venda')
        self.service.set_permissions('venda',['view','costs'],'admin',self.repo.version())
        self.assertEqual(self.service.preview_costs([],'venda')['items'],[])
        self.service.set_permissions('venda',[],'admin',self.repo.version())
        with self.assertRaises(PermissionError):self.service.preview_costs([],'venda')
        conn=self.connect()
        with conn,conn.cursor() as c:c.execute("UPDATE usuarios SET ativo=0 WHERE usuario='admin'")
        conn.close()
        with self.assertRaises(PermissionError):self.service.preview_costs([],'admin')

    def test_concurrent_publications_reject_one_stale_writer(self):
        version=self.repo.version()
        def save(code):
            try:self.service.save_draft(code,self.data(),'admin',version);return 'ok'
            except StalePreview:return 'stale'
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(save,['A','B']))
        self.assertCountEqual(results,['ok','stale'])

    def test_unconfirmed_revision_cannot_replace_active_sheet(self):
        self.activate()
        draft=self.service.save_draft('A',self.data(confirmed=False),'admin',self.repo.version())
        with self.assertRaises(PricingError):
            self.service.activate(draft['id'],'admin',self.repo.version(),uuid.uuid4().hex)
        self.assertEqual(self.repo.references(['A'])['items']['A']['price'],'200.00')

    def test_fiscal_change_blocks_old_gross_reference_until_republication(self):
        rev=self.activate(basis='GROSS')
        self.assertEqual(self.repo.references(['A'])['items']['A']['price'],'148.84')
        conn=self.connect()
        with conn,conn.cursor() as c:c.execute('UPDATE regras_fiscais SET aliquota_icms=12')
        conn.close()
        self.assertEqual(self.repo.references(['A'])['items']['A']['state'],'FISCAL_CHANGED')
        self.service.activate(rev['id'],'admin',self.repo.version(),uuid.uuid4().hex)
        self.assertEqual(self.repo.references(['A'])['items']['A']['price'],'159.72')

    def test_shared_profile_recalculates_current_sheets_and_keeps_old_snapshot(self):
        self.service.save_profile('Teste',dict(efficiency='1',taxes='0.3',rounding='CENT'),
                                  'admin',self.repo.version(),'2026-11-06',uuid.uuid4().hex)
        profile=self.repo.list_profiles()[0]
        self.activate(profile_id=profile['id'])
        old=self.repo.references(['A'])['items']['A']
        preview=self.service.preview_profile('Teste',dict(efficiency='1',taxes='0.2',rounding='CENT'),
                                             '2026-11-06','admin',self.repo.version())
        self.assertEqual(preview['items'][0]['after'],'166.67')
        self.assertEqual(self.repo.references(['A'])['items']['A']['price'],'200.00')
        self.service.save_profile('Teste',dict(efficiency='1',taxes='0.2',rounding='CENT'),
                                  'admin',preview['version'],'2026-11-06',preview['key'])
        self.assertEqual(self.repo.references(['A'])['items']['A']['price'],'166.67')
        self.assertEqual(self.repo.snapshot(old['snapshot_id'])['net_price'],'200.00')

    def test_changing_item_unit_requires_republication(self):
        self.activate()
        conn=self.connect()
        with conn,conn.cursor() as c:c.execute("UPDATE materiais SET unidade_medida='KG' WHERE codigo_material='A'")
        conn.close()
        ref=self.repo.references(['A'])['items']['A']
        self.assertEqual(ref['state'],'UNIT_CHANGED')
        self.assertIsNone(ref['price'])

    def test_archived_revision_must_be_copied_before_activation(self):
        rev=self.activate()
        self.service.archive('A','admin',self.repo.version(),'Fim da revisão',uuid.uuid4().hex)
        with self.assertRaises(PricingError):
            self.service.activate(rev['id'],'admin',self.repo.version(),uuid.uuid4().hex)

    @contextmanager
    def application_cursor(self,commit=False):
        conn=self.connect()
        try:
            with conn,conn.cursor() as c:yield c
        finally:conn.close()

    def test_fiscal_edits_invalidate_prepared_cost_publication(self):
        import database
        self.activate(basis='GROSS')
        data=self.repo.list_bases('component')[0];data['price']='110'
        preview=self.service.preview_costs([('component',data)],'admin')
        with patch('pricing_config.enabled',return_value=True),patch.object(database,'_cursor',self.application_cursor):
            database.atualizar_regra_fiscal(1,'123',12,0,'Regra alterada',1)
        with self.assertRaises(StalePreview):
            self.service.publish_costs([('component',data)],'admin',preview['version'],'Teste',preview['key'])
        self.assertEqual(self.repo.list_bases('component')[0]['price'],'100.000000000000')

    def test_item_unit_or_ncm_edit_invalidates_profile_preview(self):
        import database
        import pricing_items
        preview=self.service.preview_profile('Perfil',dict(efficiency='1',taxes='0.3',rounding='CENT'),'2026-11-06','admin',self.repo.version())
        values=dict(codigo_material='A',descricao='Teste A',ncm='456',unidade_medida='KG')
        with patch('pricing_config.enabled',return_value=True),patch.object(database,'_cursor',self.application_cursor):
            pricing_items.save_item(values,'admin')
        with self.assertRaises(StalePreview):
            self.service.save_profile('Perfil',dict(efficiency='1',taxes='0.3',rounding='CENT'),'admin',preview['version'],'2026-11-06',preview['key'])

    def test_profile_name_is_identical_in_preview_and_publication(self):
        params=dict(efficiency='1',taxes='0.3',rounding='CENT')
        self.service.save_profile('Teste',params,'admin',self.repo.version(),'2026-11-06',uuid.uuid4().hex)
        self.activate(profile_id=self.repo.list_profiles()[0]['id'])
        changed=dict(params,taxes='0.2')
        preview=self.service.preview_profile('  Teste  ',changed,'2026-11-06','admin',self.repo.version())
        self.assertEqual([x['code'] for x in preview['items']],['A'])
        result=self.service.save_profile('  Teste  ',changed,'admin',preview['version'],'2026-11-06',preview['key'])
        self.assertEqual(result['items'][0]['after'],preview['items'][0]['after'])
        self.assertEqual(len(self.repo.list_profiles()),1)

    def test_archive_event_retains_item_revision_and_reason_on_retry(self):
        revision=self.activate()
        version=self.repo.version()
        key=uuid.uuid4().hex
        first=self.service.archive('A','admin',version,'Mudou o desenho',key)
        again=self.service.archive('A','admin',version,'Mudou o desenho',key)
        self.assertEqual(first,again)
        events=[e for e in self.repo.events() if e['action']=='ARQUIVAR FOLHA']
        self.assertEqual(len(events),1)
        details=events[0]['data']['details']
        self.assertEqual(details['code'],'A')
        self.assertEqual(details['reason'],'Mudou o desenho')
        self.assertEqual(details['revisions'],[dict(id=revision['id'],number=revision['number'],previous_status='ACTIVE')])


if __name__=='__main__': unittest.main()
