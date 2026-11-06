import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
import pricing_items


class PricingScreensTests(unittest.TestCase):
    def test_switching_sheet_base_loads_new_cost_without_proposing_global_price_change(self):
        from pricing_repository import PricingRepository
        from pricing_catalog import CatalogService
        a=dict(id=1,code='A',description='Componente A',unit='UN',price='10',factor='1',active=True,version=1,reviewed_on='2026-11-06')
        b=dict(a,id=2,code='B',description='Componente B',price='100',version=2)
        data=dict(lines=[dict(kind='component',base_id=1)],margin='0.2',taxes='0',efficiency='1',commission='0',basis='NET',confirmed=True,rounding='CENT',reviewed_on='2026-11-06')
        row=dict(revision_id=1,number=1,status='DRAFT',material_code='001',descricao='Peça teste',data=data,snapshot_id=None,net_price=None,gross_price=None,reviewed_on=None)
        snapshot=dict(version=8,bases=dict(material=[],component=[a,b],process=[],service=[]),profiles=[])
        saved=[]
        def save(code,params,actor,version):saved.append(params);return dict(id=2,number=2)
        with patch.object(PricingRepository,'sheets',return_value=[row]),patch.object(PricingRepository,'catalog',return_value=snapshot), \
             patch.object(CatalogService,'permissions',return_value={'view','edit'}),patch.object(CatalogService,'save_draft',side_effect=save),patch.object(CatalogService,'preview_draft',side_effect=ValueError('Prévia indisponível na fixture')):
            app=AppTest.from_string('from pricing_sheets_ui import render_sheets\nrender_sheets("editor")',default_timeout=15).run()
            app.session_state['pricing_sheets_table']={'edited_rows':{0:{'Selecionar':True}},'added_rows':[],'deleted_rows':[]}
            app.run();next(x for x in app.button if x.label=='Editar folha').click().run()
            grid=next(d for d in app.dataframe if '_component_' in str(d.key))
            app.session_state[grid.key]={'edited_rows':{0:{'Base':'B — Componente B'}},'added_rows':[],'deleted_rows':[]}
            app.run()
            grid=next(d for d in app.dataframe if '_component_' in str(d.key))
            self.assertEqual(grid.value.iloc[0]['Preço (R$)'],'100')
            next(x for x in app.button if x.label=='Salvar rascunho').click().run()
            self.assertEqual(len(app.exception),0)
            self.assertEqual(saved[0]['proposed_prices'],[])
            self.assertEqual(saved[0]['lines'][0]['base_id'],2)

    def test_sheet_automatic_price_preserves_edited_margin_and_time(self):
        from pricing_repository import PricingRepository
        from pricing_catalog import CatalogService
        base=dict(id=1,code='MDO',description='Operação',unit='H',price='60',factor='1',active=True,per_person=True,reviewed_on='2026-11-06',version=1)
        data=dict(lines=[dict(kind='process',base_id=1,minutes='10')],margin='0.2',taxes='0',efficiency='1',commission='0',tool_cost='0',basis='NET',confirmed=True,rounding='CENT',reviewed_on='2026-11-06')
        row=dict(revision_id=1,number=1,status='DRAFT',material_code='001',descricao='Peça teste',unidade_medida='UN',data=data,snapshot_id=None,net_price=None,gross_price=None,reviewed_on=None)
        profile=dict(id=1,code='GERAL',data=dict(efficiency='0.65',taxes='0.3',rounding='CENT'),active=True,version=1,reviewed_on='2026-11-06')
        snapshot=dict(version=8,bases=dict(material=[],component=[],process=[base],service=[]),profiles=[profile])
        calculation=dict(cost='10',gross_price='12.50',net_price='12.50',reviewed_on='2026-11-06',breakdown=dict(material='0',component='0',process='10',service='0',tool='0'),lines=[])
        payloads=[]
        def preview(code,params,actor,version):payloads.append(params);return dict(calculation=calculation)
        with patch.object(PricingRepository,'sheets',return_value=[row]),patch.object(PricingRepository,'catalog',return_value=snapshot), \
             patch.object(CatalogService,'permissions',return_value={'view','edit','costs'}), \
             patch.object(CatalogService,'preview_draft',side_effect=preview):
            app=AppTest.from_string('from pricing_sheets_ui import render_sheets\nrender_sheets("admin")',default_timeout=15).run()
            app.session_state['pricing_sheets_table']={'edited_rows':{0:{'Selecionar':True}},'added_rows':[],'deleted_rows':[]}
            app.run();next(b for b in app.button if b.label=='Editar folha').click().run()
            next(n for n in app.number_input if n.label=='Margem bruta (%)').set_value(35)
            grid=next(d for d in app.dataframe if 'Minutos' in d.value.columns)
            app.session_state[grid.key]={'edited_rows':{0:{'Minutos':25}},'added_rows':[],'deleted_rows':[]}
            next(b for b in app.button if b.label=='Simular composição').click().run()
            self.assertFalse(any(s.label=='Perfil compartilhado de cálculo' for s in app.selectbox))
            next(b for b in app.button if b.label=='Simular composição').click().run()
            self.assertEqual(len(app.exception),0)
            self.assertEqual(payloads[-1]['margin'],'0.35')
            self.assertEqual(float(payloads[-1]['lines'][0]['minutes']),25)
            self.assertEqual(payloads[-1]['efficiency'],'1.0')
            self.assertTrue(any(m.label=='Preço unitário líquido KSB' for m in app.metric))

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
             patch.object(PricingService,'preview_draft',return_value=dict(calculation=calculation)), \
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
    def test_unified_form_keeps_edits_adds_field_and_saves_all_once(self):
        from pricing_catalog import CatalogService
        from pricing_repository import PricingRepository
        def base(id,code,price):return dict(id=id,code=code,description=code,unit='UN',price=price,factor='1',reviewed_on='2026-11-01',active=True,per_person=True,version=1,note='',usage_count=0)
        snapshot=dict(version=8,bases=dict(component=[base(1,'PARAFUSO','10'),base(2,'PORCA','2')],material=[],process=[],service=[]),
                      profiles=[dict(id=1,code='GERAL',data=dict(efficiency='1',taxes='0.3',rounding='CENT'),active=True,reviewed_on='2026-11-01',version=1,usage_count=0)])
        saved=[]
        def publish(changes,profiles,deletions,actor,version,reason,key):
            saved.append((changes,profiles,version));return dict(count=2)
        with patch.object(PricingRepository,'catalog',return_value=snapshot), \
             patch.object(CatalogService,'permissions',return_value={'view','costs'}), \
             patch.object(CatalogService,'publish_catalog',side_effect=publish):
            source='import streamlit as st\nfrom pricing_catalog_ui import render_catalog\narea=st.radio("Tela",["Central","Outra"],key="central_test_route")\nif area=="Central":render_catalog("admin")'
            app=AppTest.from_string(source,default_timeout=15).run()
            self.assertEqual(len(app.exception),0)
            self.assertEqual(len(app.dataframe),0)
            next(t for t in app.text_input if t.label=='PARAFUSO (R$/un)').set_value('13').run()
            next(t for t in app.text_input if t.label=='PORCA (R$/un)').set_value('3,50').run()
            self.assertFalse(any('Tributos de venda' in t.label for t in app.text_input))
            next(t for t in app.text_input if t.label=='Nome do novo campo').set_value('ARRUELA')
            next(t for t in app.text_input if t.label=='Preço inicial (R$)').set_value('4')
            next(b for b in app.button if b.label=='Adicionar campo').click().run()
            self.assertEqual(len(app.exception),0)
            self.assertEqual(next(t for t in app.text_input if t.label=='PARAFUSO (R$/un)').value,'13')
            self.assertTrue(any(t.label=='ARRUELA (R$/un)' for t in app.text_input))
            self.assertEqual(saved,[])
            app.radio(key='central_test_route').set_value('Outra').run()
            app.radio(key='central_test_route').set_value('Central').run()
            self.assertEqual(next(t for t in app.text_input if t.label=='PORCA (R$/un)').value,'3,50')
            next(b for b in app.button if b.label=='Salvar alterações').click().run()
            self.assertEqual(len(app.exception),0)
            self.assertEqual([r['price'] for _,r in saved[0][0]],['13','3.50','4'])
            self.assertEqual(saved[0][1],[])
            self.assertEqual(saved[0][2],8)
            self.assertTrue(any('2 itens' in s.value for s in app.success))

    def test_referenced_form_field_cannot_be_removed_but_its_price_is_editable(self):
        from pricing_catalog import CatalogService
        from pricing_repository import PricingRepository
        base=dict(id=1,code='PARAFUSO',description='Parafuso X',unit='UN',price='10',factor='1',active=True,per_person=True,version=1,reviewed_on='2026-11-01',note='',usage_count=2)
        with patch.object(PricingRepository,'catalog',return_value=dict(version=8,bases=dict(component=[base],material=[],process=[],service=[]),profiles=[])), \
             patch.object(CatalogService,'permissions',return_value={'view','costs'}):
            app=AppTest.from_string('from pricing_catalog_ui import render_catalog\nrender_catalog("admin")',default_timeout=15).run()
            self.assertEqual(len(app.exception),0)
            self.assertFalse(next(t for t in app.text_input if t.label=='Parafuso X (R$/un)').disabled)
            self.assertTrue(next(c for c in app.checkbox if c.label=='Remover campo').disabled)
            self.assertTrue(any('vinculado' in c.value.lower() for c in app.caption))

    def test_free_form_field_removal_is_sent_only_on_save(self):
        from pricing_catalog import CatalogService
        from pricing_repository import PricingRepository
        base=dict(id=1,code='LIVRE',description='Campo livre',unit='UN',price='10',factor='1',active=True,per_person=True,version=1,reviewed_on='2026-11-01',note='',usage_count=0)
        saved=[]
        def publish(changes,profiles,deletions,actor,version,reason,key):
            saved.append(deletions);return dict(count=0)
        with patch.object(PricingRepository,'catalog',return_value=dict(version=8,bases=dict(component=[base],material=[],process=[],service=[]),profiles=[])), \
             patch.object(CatalogService,'permissions',return_value={'view','costs'}), \
             patch.object(CatalogService,'publish_catalog',side_effect=publish):
            app=AppTest.from_string('from pricing_catalog_ui import render_catalog\nrender_catalog("admin")',default_timeout=15).run()
            next(c for c in app.checkbox if c.label=='Remover campo').check().run()
            self.assertEqual(saved,[])
            next(b for b in app.button if b.label=='Salvar alterações').click().run()
            self.assertEqual(len(app.exception),0)
            self.assertEqual(saved,[[('component',1)]])

    def test_invalid_form_value_is_retained_after_save_failure(self):
        from pricing_catalog import CatalogService
        from pricing_repository import PricingRepository
        base=dict(id=1,code='P',description='Parafuso',unit='UN',price='10',factor='1',active=True,per_person=True,version=1,reviewed_on='2026-11-01',note='',usage_count=0)
        with patch.object(PricingRepository,'catalog',return_value=dict(version=8,bases=dict(component=[base],material=[],process=[],service=[]),profiles=[])), \
             patch.object(CatalogService,'permissions',return_value={'view','costs'}):
            app=AppTest.from_string('from pricing_catalog_ui import render_catalog\nrender_catalog("admin")',default_timeout=15).run()
            next(t for t in app.text_input if t.label=='Parafuso (R$/un)').set_value('inválido').run()
            next(b for b in app.button if b.label=='Salvar alterações').click().run()
            self.assertEqual(len(app.exception),0)
            self.assertEqual(next(t for t in app.text_input if t.label=='Parafuso (R$/un)').value,'inválido')
            self.assertTrue(app.error)

    def test_saved_draft_opens_immediately_for_review_without_manual_refresh(self):
        from pricing_repository import PricingRepository
        from pricing_catalog import CatalogService
        records=[]
        def save(code,data,actor,version):
            records.append(dict(revision_id=42,number=1,status='DRAFT',material_code=code,descricao='Peça teste',unidade_medida='UN',data=data,snapshot_id=None,net_price=None,gross_price=None,reviewed_on=None))
            return dict(id=42,number=1)
        with patch.object(PricingRepository,'sheets',side_effect=lambda:records), \
             patch.object(PricingRepository,'catalog',return_value=dict(version=8,bases=dict(material=[],component=[],process=[],service=[]),profiles=[])), \
             patch.object(CatalogService,'permissions',return_value={'view','edit','publish','costs'}), \
             patch.object(CatalogService,'save_draft',side_effect=save), \
             patch.object(CatalogService,'preview_draft',side_effect=ValueError('Rascunho incompleto')), \
             patch.object(CatalogService,'preview_sheet',side_effect=ValueError('Rascunho incompleto')):
            app=AppTest.from_string('from pricing_sheets_ui import render_sheets\nrender_sheets("admin")',default_timeout=15)
            app.session_state['pricing_sheet_request']='001'
            app.run()
            next(b for b in app.button if b.label=='Salvar rascunho').click().run()
            self.assertEqual(len(app.exception),0)
            self.assertEqual(app.session_state['pricing_sheet_open']['row']['revision_id'],42)
            self.assertTrue(any(b.label=='Publicar revisão' for b in app.button))

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

    def test_pricing_navigation_uses_buttons_without_profile_page(self):
        from pricing_repository import PricingRepository
        from pricing_catalog import CatalogService
        snapshot=dict(version=0,bases=dict(material=[],component=[],process=[],service=[]),profiles=[])
        with patch.object(PricingRepository,'catalog',return_value=snapshot),patch.object(PricingRepository,'sheets',return_value=[]),patch.object(PricingRepository,'version',return_value=0),patch.object(CatalogService,'permissions',return_value={'view','costs'}):
            app=AppTest.from_string('from pricing_ui import render_pricing\nrender_pricing("admin")',default_timeout=15).run()
            self.assertEqual(len(app.exception),0)
            self.assertEqual(len(app.radio),0)
            next(b for b in app.button if b.label=='Central de custos').click().run()
            self.assertTrue(any(b.label=='Salvar alterações' for b in app.button))
            self.assertFalse(any('perfil' in b.label.lower() for b in app.button))
            next(b for b in app.button if b.label=='Folhas de processo').click().run()
            self.assertTrue(any(b.label=='Nova folha' for b in app.button))

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
             patch.object(PricingRepository,'events',return_value=[]), \
             patch.object(PricingService,'preview_draft',side_effect=ValueError('Inclua uma composição')):
            app=AppTest.from_string('from pricing_ui import render_pricing\nrender_pricing("editor")',default_timeout=15).run()
            self.assertEqual(len(app.exception),0)
            next(b for b in app.button if b.label=='Nova folha').click().run()
            next(s for s in app.selectbox if s.label=='Item KSB da folha').select('001').run()
            self.assertEqual(len(app.exception),0)
            self.assertFalse(any(s.label=='Base comercial do PV' for s in app.selectbox))

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
