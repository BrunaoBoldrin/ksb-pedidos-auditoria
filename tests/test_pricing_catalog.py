"""Real PostgreSQL workflows for one-save universal costs and user permissions."""
import os
import unittest
import uuid

from pricing_catalog import CatalogService
from pricing_calculator import PricingError
from pricing_service import StalePreview
import test_pricing_repository as fixtures


@unittest.skipUnless(os.environ.get('PRICING_TEST_DSN'),'PostgreSQL de teste não configurado')
class CatalogTests(unittest.TestCase):
    tearDown=fixtures.RepositoryTests.tearDown
    data=fixtures.RepositoryTests.data
    activate=fixtures.RepositoryTests.activate

    def setUp(self):
        fixtures.RepositoryTests.setUp(self)
        self.catalog=CatalogService(self.repo)
        with self.repo.transaction() as c:c.execute('ALTER TABLE usuarios ADD COLUMN senha text')

    def key(self):return uuid.uuid4().hex

    def test_cost_and_profile_update_publish_shared_sheet_once_and_retry_is_idempotent(self):
        self.service.save_profile('Geral',dict(efficiency='1',taxes='0.3',rounding='CENT'),'admin',self.repo.version(),'2026-11-06',self.key())
        profile=self.repo.list_profiles()[0]
        self.activate(profile_id=profile['id'])
        before=self.repo.references(['A'])['items']['A']
        base=self.repo.list_bases('component')[0];base['price']='110'
        profile['data']['taxes']='0.2'
        version=self.repo.version();key=self.key()
        preview=self.catalog.preview_catalog([('component',base)],[profile],[],'admin',version)
        self.assertEqual(preview['items'][0]['after'],'183.33')
        self.assertEqual(self.repo.references(['A'])['items']['A']['price'],'200.00')
        result=self.catalog.publish_catalog([('component',base)],[profile],[],'admin',version,'Atualização',key)
        self.assertEqual(result['count'],1)
        self.assertEqual(self.repo.references(['A'])['items']['A']['price'],'183.33')
        self.assertEqual(self.repo.snapshot(before['snapshot_id'])['net_price'],'200.00')
        self.assertEqual(self.catalog.publish_catalog([('component',base)],[profile],[],'admin',version,'Atualização',key),result)
        with self.repo.transaction() as c:
            c.execute('SELECT count(*) AS n FROM pricing_prices WHERE revision_id=%s',(before['revision_id'],))
            self.assertEqual(c.fetchone()['n'],2)

    def test_invalid_row_rolls_back_all_universal_cost_edits(self):
        self.activate()
        base=self.repo.list_bases('component')[0];base['price']='110'
        bad=dict(code='INVALIDO',description='Teste',unit='UN',price='-1',reviewed_on='2026-11-06')
        version=self.repo.version()
        with self.assertRaises(PricingError):
            self.catalog.publish_catalog([('component',base),('material',bad)],[],[],'admin',version,'Teste',self.key())
        self.assertEqual(self.repo.references(['A'])['items']['A']['price'],'200.00')
        self.assertEqual(self.repo.version(),version)

    def test_delete_used_cost_is_rejected_and_unused_cost_can_be_blocked_and_deleted(self):
        self.activate()
        with self.assertRaises(PricingError):
            self.catalog.publish_catalog([],[],[('component',self.base['id'])],'admin',self.repo.version(),'Excluir',self.key())
        base=dict(code='LIVRE',description='Sem vínculo',unit='UN',price='10',reviewed_on='2026-11-06')
        self.catalog.publish_catalog([('material',base)],[],[],'admin',self.repo.version(),'Novo',self.key())
        row=self.repo.list_bases('material')[0];row['active']=False
        self.catalog.publish_catalog([('material',row)],[],[],'admin',self.repo.version(),'Bloquear',self.key())
        self.assertFalse(self.repo.list_bases('material')[0]['active'])
        self.catalog.publish_catalog([],[],[('material',row['id'])],'admin',self.repo.version(),'Excluir',self.key())
        self.assertEqual(self.repo.list_bases('material'),[])

    def test_profile_lifecycle_preserves_referenced_profiles(self):
        profile=dict(code='Geral',data=dict(efficiency='1',taxes='0.3',rounding='CENT'),reviewed_on='2026-11-06',active=True)
        self.catalog.publish_catalog([], [profile], [], 'admin',self.repo.version(),'Novo',self.key())
        profile=self.repo.list_profiles()[0]
        self.activate(profile_id=profile['id'])
        with self.assertRaises(PricingError):
            self.catalog.publish_catalog([],[],[('profile',profile['id'])],'admin',self.repo.version(),'Excluir',self.key())
        profile['active']=False
        with self.assertRaises(PricingError):
            self.catalog.publish_catalog([],[profile],[],'admin',self.repo.version(),'Bloquear',self.key())
        self.assertTrue(self.repo.list_profiles()[0]['active'])

    def test_catalog_save_checks_original_version_and_current_permissions(self):
        base=self.repo.list_bases('component')[0];base['price']='13'
        version=self.repo.version()
        self.service.save_draft('A',self.data(),'admin',version)
        with self.assertRaises(StalePreview):
            self.catalog.publish_catalog([('component',base)],[],[],'admin',version,'Teste',self.key())
        with self.assertRaises(PermissionError):
            self.catalog.publish_catalog([('component',base)],[],[],'venda',self.repo.version(),'Teste',self.key())

    def test_user_edit_saves_profile_status_and_permissions_together_including_blocked_user(self):
        with self.repo.transaction() as c:
            c.execute("SELECT id FROM usuarios WHERE usuario='venda'");uid=c.fetchone()['id']
        self.catalog.save_user(uid,dict(name='Vendas',username='venda',profile='PROCESSISTA',active=False),['view','edit','costs'],'admin',self.repo.version())
        users=self.catalog.users('admin')
        row=next(u for u in users if u['id']==uid)
        self.assertEqual(row['permissions'],['costs','edit','view'])
        self.assertEqual(row['perfil'],'PROCESSISTA')
        self.assertEqual(row['ativo'],0)
        with self.assertRaises(PermissionError):self.service.permissions('venda')

    def test_catalog_snapshot_and_sheet_list_are_consistent(self):
        revision=self.activate()
        snap=self.repo.catalog()
        self.assertEqual(snap['version'],self.repo.version())
        self.assertEqual(snap['bases']['component'][0]['code'],'COMP')
        rows=self.repo.sheets()
        self.assertEqual(rows[0]['revision_id'],revision['id'])
        self.assertEqual(rows[0]['net_price'],'200.00')

    def test_catalog_usage_counts_include_archived_and_draft_links(self):
        self.activate()
        self.service.archive('A','admin',self.repo.version(),'Histórico',self.key())
        self.service.save_draft('B',self.data(),'admin',self.repo.version())
        snapshot=self.repo.catalog()
        self.assertEqual(snapshot['bases']['component'][0]['usage_count'],2)
        with self.assertRaises(PricingError):
            self.catalog.publish_catalog([],[],[('component',self.base['id'])],'admin',self.repo.version(),'Excluir',self.key())

    def test_blocked_profile_cannot_be_used_to_publish_new_sheet(self):
        profile=dict(code='Bloqueado',data=dict(efficiency='1',taxes='0.3',rounding='CENT'),reviewed_on='2026-11-06',active=False)
        self.catalog.publish_catalog([],[profile],[],'admin',self.repo.version(),'Novo bloqueado',self.key())
        draft=self.service.save_draft('A',self.data(profile_id=self.repo.list_profiles()[0]['id']),'admin',self.repo.version())
        with self.assertRaises(PricingError):
            self.service.activate(draft['id'],'admin',self.repo.version(),self.key())

    def test_user_lifecycle_preserves_admin_and_never_logs_passwords(self):
        uid=self.catalog.save_user(None,dict(name='Novo',username='novo',profile='PROCESSISTA',active=True,password='fake-initial-password'),['edit'],'admin',self.repo.version())
        self.assertEqual(self.service.permissions('novo'),{'view','edit'})
        self.catalog.user_action(uid,'password','admin',self.repo.version(),'fake-replacement-password')
        with self.repo.transaction() as c:
            c.execute('SELECT senha FROM usuarios WHERE id=%s',(uid,))
            self.assertEqual(c.fetchone()['senha'],'fake-replacement-password')
        self.assertNotIn('fake-replacement-password',str(self.repo.events()))
        self.catalog.user_action(uid,'delete','admin',self.repo.version())
        self.assertFalse(any(u['id']==uid for u in self.catalog.users('admin')))
        admin=next(u for u in self.catalog.users('admin') if u['usuario']=='admin')
        with self.assertRaises(PricingError):
            self.catalog.user_action(admin['id'],'delete','admin',self.repo.version())

    def proposal(self,price='130'):
        base=self.repo.list_bases('component')[0]
        return [dict(kind='component',base_id=base['id'],price=price,version=base['version'],reviewed_on='2026-11-06')]

    def test_sheet_price_edit_is_draft_only_until_publication_updates_every_dependent(self):
        self.activate('A');self.activate('B')
        draft=self.service.save_draft('A',self.data(proposed_prices=self.proposal()),'admin',self.repo.version())
        self.assertEqual(self.repo.references(['A'])['items']['A']['price'],'200.00')
        self.assertEqual(self.service.preview_sheet(draft['id'],'admin')['calculation']['net_price'],'260.00')
        self.assertEqual(self.repo.list_bases('component')[0]['price'],'100.000000000000')
        result=self.service.activate(draft['id'],'admin',self.repo.version(),self.key())
        self.assertEqual(result['count'],2)
        refs=self.repo.references(['A','B'])['items']
        self.assertEqual([refs[c]['price'] for c in ('A','B')],['260.00','260.00'])

    def test_stale_sheet_price_proposal_never_overwrites_newer_universal_cost(self):
        self.activate('A')
        draft=self.service.save_draft('A',self.data(proposed_prices=self.proposal()),'admin',self.repo.version())
        base=self.repo.list_bases('component')[0];base['price']='110'
        self.catalog.publish_catalog([('component',base)],[],[],'admin',self.repo.version(),'Atualização',self.key())
        with self.assertRaises(StalePreview):self.service.activate(draft['id'],'admin',self.repo.version(),self.key())
        self.assertEqual(self.repo.references(['A'])['items']['A']['price'],'220.00')

    def test_active_sheet_recalculation_does_not_replay_old_proposed_cost(self):
        draft=self.service.save_draft('A',self.data(proposed_prices=self.proposal()),'admin',self.repo.version())
        self.service.activate(draft['id'],'admin',self.repo.version(),self.key())
        base=self.repo.list_bases('component')[0];base['price']='140'
        self.catalog.publish_catalog([('component',base)],[],[],'admin',self.repo.version(),'Atualização',self.key())
        self.service.activate(draft['id'],'admin',self.repo.version(),self.key())
        self.assertEqual(self.repo.references(['A'])['items']['A']['price'],'280.00')

    def test_failed_sheet_publication_rolls_back_proposed_global_price(self):
        self.activate()
        draft=self.service.save_draft('A',self.data(proposed_prices=self.proposal(),efficiency='0'),'admin',self.repo.version())
        with self.assertRaises(PricingError):self.service.activate(draft['id'],'admin',self.repo.version(),self.key())
        self.assertEqual(self.repo.references(['A'])['items']['A']['price'],'200.00')
        self.assertEqual(self.repo.list_bases('component')[0]['price'],'100.000000000000')

    def test_sheet_price_edit_requires_cost_permission_at_save_and_publish(self):
        data=self.data(proposed_prices=self.proposal())
        self.service.set_permissions('venda',['view','edit','publish'],'admin',self.repo.version())
        with self.assertRaises(PermissionError):self.service.save_draft('A',data,'venda',self.repo.version())
        draft=self.service.save_draft('A',data,'admin',self.repo.version())
        with self.assertRaises(PermissionError):self.service.activate(draft['id'],'venda',self.repo.version(),self.key())
