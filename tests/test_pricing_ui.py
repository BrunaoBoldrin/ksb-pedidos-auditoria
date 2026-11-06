import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
import pricing_items


class PricingScreensTests(unittest.TestCase):
    def test_sheet_list_checkbox_opens_worksheet_and_can_edit_times_and_margin(self):
        from pricing_repository import PricingRepository
        from pricing_service import PricingService
        from pricing_catalog import CatalogService
        base=dict(id=1,code='MDO',description='Operação',unit='H',price='60',factor='1',active=True,per_person=True,reviewed_on='2026-11-06',version=1)
        data=dict(lines=[dict(kind='process',base_id=1,hours='0',minutes='10',people='1')],margin='0.2',taxes='0',efficiency='1',commission='0',tool_cost='0',basis='NET',confirmed=True,rounding='CENT',reviewed_on='2026-11-06')
        row=dict(revision_id=1,number=1,status='DRAFT',material_code='001',descricao='Peça teste',unidade_medida='UN',data=data,snapshot_id=None,net_price=None,gross_price=None,reviewed_on=None)
        snap=dict(version=8,bases=dict(material=[],component=[],process=[base],service=[]),profiles=[])
        calculation=dict(cost='10',gross_price='12.50',net_price='12.50',reviewed_on='2026-11-06',breakdown=dict(material='0',component='0',process='10',service='0',tool='0'),lines=[])
        with patch.object(PricingRepository,'sheets',return_value=[row]), \
             patch.object(PricingRepository,'catalog',return_value=snap), \
             patch.object(CatalogService,'permissions',return_value={'view','edit','publish','costs'}), \
             patch.object(PricingService,'preview_sheet',return_value=dict(calculation=calculation)) as preview:
            app=AppTest.from_string('from pricing_sheets_ui import render_sheets\nrender_sheets("admin")',default_timeout=15).run()
            self.assertEqual(len(app.exception),0)
            app.session_state['pricing_sheets_table']={'edited_rows':{0:{'Selecionar':True}},'added_rows':[],'deleted_rows':[]}
            app.run()
            next(b for b in app.button if b.label=='Visualizar folha').click().run()
            self.assertEqual(len(app.exception),0)
            self.assertTrue(any('FOLHA DE PROCESSO' in m.value for m in app.markdown))
            preview.side_effect=ValueError('Composição incompleta')
            app.run()
            self.assertTrue(any('Minutos' in d.value.columns for d in app.dataframe))
            preview.side_effect=None
            next(b for b in app.button if b.label=='Editar folha').click().run()
            self.assertEqual(len(app.exception),0)
            self.assertTrue(any(n.label=='Margem bruta (%)' for n in app.number_input))
            self.assertTrue(any('Minutos' in d.value.columns for d in app.dataframe))
    def test_unified_grid_saves_two_costs_and_profile_with_one_action(self):
        from pricing_catalog import CatalogService
        from pricing_repository import PricingRepository
        def base(id,code,price):return dict(id=id,code=code,description=code,unit='UN',price=price,factor='1',reviewed_on='2026-11-01',active=True,per_person=True,version=1,note='')
        snapshot=dict(version=8,bases=dict(component=[base(1,'PARAFUSO','10'),base(2,'PORCA','2')],material=[],process=[],service=[]),
                      profiles=[dict(id=1,code='GERAL',data=dict(efficiency='1',taxes='0.3',rounding='CENT'),active=True,reviewed_on='2026-11-01',version=1)])
        saved=[]
        def publish(changes,profiles,deletions,actor,version,reason,key):
            saved.append((changes,profiles,version));return dict(count=2)
        with patch.object(PricingRepository,'catalog',return_value=snapshot), \
             patch.object(CatalogService,'permissions',return_value={'view','costs'}), \
             patch.object(CatalogService,'publish_catalog',side_effect=publish):
            app=AppTest.from_string('from pricing_catalog_ui import render_catalog\nrender_catalog("admin")',default_timeout=15).run()
            self.assertEqual(len(app.exception),0)
            app.session_state['catalog_costs_admin_all_0']={'edited_rows':{0:{'Preço (R$)':'13'}},'added_rows':[],'deleted_rows':[]}
            app.run()
            app.session_state['catalog_costs_admin_all_0']={'edited_rows':{0:{'Preço (R$)':'13'},1:{'Preço (R$)':'3,50'}},'added_rows':[],'deleted_rows':[]}
            app.session_state['catalog_profiles_admin_all_0']={'edited_rows':{0:{'Impostos (%)':'20'}},'added_rows':[],'deleted_rows':[]}
            app.run()
            next(b for b in app.button if b.label=='Salvar alterações').click().run()
            self.assertEqual(len(app.exception),0)
            self.assertEqual([r['price'] for _,r in saved[0][0]],['13','3.50'])
            self.assertEqual(saved[0][1][0]['data']['taxes'],'0.2')
            self.assertEqual(saved[0][2],8)
            self.assertTrue(any('2 itens' in s.value for s in app.success))

    def test_technical_checkbox_selection_opens_selected_item_without_second_selector(self):
        with patch.object(pricing_items,'list_items',return_value=[('00123','Peça teste','','','123','UN','J1','V1')]):
            app=AppTest.from_string('from pricing_ui import render_items\nrender_items("editor",True,True)',default_timeout=15).run()
            self.assertEqual(len(app.exception),0)
            self.assertFalse(any(s.label=='Selecionar item' for s in app.selectbox))
            self.assertIn('Selecionar',app.dataframe[0].value.columns)
            app.session_state['technical_table']={'edited_rows':{0:{'Selecionar':True}},'added_rows':[],'deleted_rows':[]}
            app.run()
            next(b for b in app.button if b.label=='Editar selecionado').click().run()
            self.assertEqual(len(app.exception),0)
            self.assertEqual(app.text_input(key='technical_codigo_material').value,'00123')

    def test_user_permissions_appear_only_inside_selected_user_edit_form(self):
        from pricing_catalog import CatalogService
        from pricing_repository import PricingRepository
        users=[dict(id=2,nome='Vendas',usuario='venda',perfil='VENDEDORA',ativo=1,permissions=['view'])]
        with patch.object(CatalogService,'users',return_value=users), \
             patch.object(CatalogService,'permissions',return_value={'permissions','view'}), \
             patch.object(PricingRepository,'version',return_value=3):
            app=AppTest.from_string('from pricing_users import render_users\nrender_users("admin")',default_timeout=15).run()
            self.assertEqual(len(app.exception),0)
            self.assertFalse(any(c.label=='Consultar custos e composição' for c in app.checkbox))
            app.session_state['pricing_users_table']={'edited_rows':{0:{'Selecionar':True}},'added_rows':[],'deleted_rows':[]}
            app.run()
            next(b for b in app.button if b.label=='✏️ Editar Usuário').click().run()
            self.assertEqual(len(app.exception),0)
            self.assertTrue(next(c for c in app.checkbox if c.label=='Consultar custos e composição').value)
            self.assertEqual(next(t for t in app.text_input if t.label=='Usuário').value,'venda')

    def test_switching_profile_does_not_reuse_another_profiles_unsaved_values(self):
        from pricing_repository import PricingRepository
        from pricing_catalog import CatalogService
        profiles=[dict(id=i,code=name,reviewed_on='2026-11-06',active=True,version=1,data=dict(efficiency='1',taxes='0.3',rounding='CENT')) for i,name in [(1,'A'),(2,'B')]]
        with patch.object(PricingRepository,'catalog',return_value=dict(version=0,bases=dict(material=[],component=[],process=[],service=[]),profiles=profiles)), \
             patch.object(CatalogService,'permissions',return_value={'view','costs'}):
            app=AppTest.from_string('from pricing_catalog_ui import render_catalog\nrender_catalog("editor",profiles_only=True)',default_timeout=15).run()
            self.assertEqual(len(app.exception),0)
            app.session_state['catalog_profiles_editor_profiles_0']={'edited_rows':{0:{'Eficiência (%)':'50'},1:{'Selecionar':True}},'added_rows':[],'deleted_rows':[]}
            app.run()
            app.button(key='edit_profile').click().run()
            self.assertEqual(len(app.exception),0)
            self.assertEqual(next(t for t in app.text_input if t.label=='Perfil').value,'B')
            self.assertEqual(next(t for t in app.text_input if t.label=='Eficiência (%)').value,'100')

    def test_cost_editor_and_sheet_editor_render_with_empty_catalogs(self):
        class Repo:
            def version(self):return 0
            def revisions(self,code):return []
            def list_bases(self,kind):return []
            def list_profiles(self):return []
            def references(self,codes):return dict(version=0,items={})
            def events(self):return []
        from pricing_service import PricingService
        from pricing_repository import PricingRepository
        with patch.object(pricing_items,'list_items',return_value=[('001','Peça teste','','','123','UN','','')]), \
             patch.object(PricingService,'permissions',return_value={'view','edit','publish','costs'}), \
             patch.object(PricingRepository,'version',return_value=0), \
             patch.object(PricingRepository,'sheets',return_value=[]), \
             patch.object(PricingRepository,'catalog',return_value=dict(version=0,bases=dict(material=[],component=[],process=[],service=[]),profiles=[])), \
             patch.object(PricingRepository,'revisions',return_value=[]), \
             patch.object(PricingRepository,'list_bases',return_value=[]), \
             patch.object(PricingRepository,'list_profiles',return_value=[]), \
             patch.object(PricingRepository,'references',return_value=dict(version=0,items={})), \
             patch.object(PricingRepository,'events',return_value=[]):
            app=AppTest.from_string('from pricing_ui import render_pricing\nrender_pricing("editor")',default_timeout=15).run()
            self.assertEqual(len(app.exception),0)
            next(b for b in app.button if b.label=='Nova folha').click().run()
            next(s for s in app.selectbox if s.label=='Item KSB da folha').select('001').run()
            self.assertEqual(len(app.exception),0)
            self.assertTrue(any(s.label=='Base comercial do PV' for s in app.selectbox))

    def test_item_form_and_table_have_no_price_and_save_only_technical_fields(self):
        saved=[]
        with patch.object(pricing_items,'list_items',return_value=[]), \
             patch.object(pricing_items,'save_item',side_effect=lambda data,actor:saved.append(data)):
            app=AppTest.from_string('from pricing_ui import render_items\nrender_items("editor", True, False)',default_timeout=15).run()
            self.assertEqual(len(app.exception),0)
            app.button(key='technical_new').click().run()
            labels=[x.label for x in app.text_input]+[x.label for x in app.number_input]
            self.assertFalse(any('preço' in x.lower() for x in labels))
            app.text_input(key='technical_codigo_material').set_value('00123')
            app.text_input(key='technical_descricao').set_value('Peça fictícia')
            app.button(key='technical_save').click().run()
            self.assertEqual(len(app.exception),0)
            self.assertEqual(saved[0]['codigo_material'],'00123')
            self.assertEqual(set(saved[0]),set(pricing_items.FIELDS))

    def test_user_without_cost_permission_cannot_open_composition(self):
        with patch('pricing_service.PricingService.permissions',return_value=set()):
            app=AppTest.from_string('from pricing_ui import render_pricing\nrender_pricing("viewer")',default_timeout=15).run()
            self.assertEqual(len(app.exception),0)
            self.assertTrue(any('autorização' in e.value for e in app.error))
            self.assertEqual(len(app.dataframe),0)


if __name__=='__main__':unittest.main()
