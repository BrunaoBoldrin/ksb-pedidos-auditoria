"""Protect batch payloads and drafts at the real Streamlit editor boundary."""
import unittest
from copy import deepcopy
from contextlib import ExitStack
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from pricing_catalog import CatalogService
from pricing_repository import PricingRepository
from pricing_service import StalePreview


class CatalogGridTests(unittest.TestCase):
    def setUp(self):
        def base(id,code,price,usage=0):
            return dict(id=id,code=code,description=code,unit='UN',price=price,factor='1',kg_m2=None,
                        length_mm=None,active=True,per_person=True,reviewed_on='2026-11-01',
                        version=1,note='',usage_count=usage)
        self.snapshot=dict(version=8,bases=dict(component=[base(1,'PARAFUSO','10',2),base(2,'PORCA','2')],
                            material=[dict(base(1,'CHAPA','25'),unit='KG',kg_m2='7.123456789012')],process=[],service=[]),profiles=[])
        self.saved=[]
        self.failure=None
        self.permissions={'view','costs'}
        def publish(changes,profiles,deletions,actor,version,reason,key):
            if self.failure:raise self.failure
            self.saved.append(dict(changes=changes,profiles=profiles,deletions=deletions,version=version,actor=actor,key=key))
            return dict(count=2)
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(PricingRepository,'catalog',side_effect=lambda:deepcopy(self.snapshot)))
        self.stack.enter_context(patch.object(CatalogService,'permissions',side_effect=lambda actor:self.permissions))
        self.stack.enter_context(patch.object(CatalogService,'publish_catalog',side_effect=publish))
        self.source='import streamlit as st\nfrom pricing_catalog_ui import render_catalog\npage=st.radio("Tela",["Central","Outra"],key="test_route")\nif page=="Central":render_catalog("admin")'

    def app(self):
        app=AppTest.from_string(self.source,default_timeout=20).run()
        self.assertEqual(len(app.exception),0)
        return app

    def grid(self,app,kind):
        matches=[d for d in app.dataframe if f'_grid_{kind}_' in str(d.key)]
        self.assertEqual(len(matches),1,'Cada tipo deve ter uma miniplanilha editável')
        return matches[0]

    def edit(self,app,kind,edits=None,added=None):
        app.session_state[self.grid(app,kind).key]={'edited_rows':edits or {},'added_rows':added or [],'deleted_rows':[]}

    def button(self,app,label):return next(b for b in app.button if b.label==label)

    def draft(self,app,kind):
        # AppTest.dataframe.value is the unedited input table, not client cells.
        return [row for row in app.session_state['grid_catalog_workspace_admin']['costs'] if row['_key'].startswith(kind+':')]

    def test_four_grids_add_multiple_rows_and_save_all_categories_once(self):
        app=self.app()
        self.assertEqual(len(app.dataframe),4)
        self.edit(app,'component',{0:{'Preço (R$)':'13,123456789012'},1:{'Preço (R$)':'3,50'}})
        self.button(app,'+ Linha · Matérias-primas').click().run()
        self.assertEqual(len(app.exception),0)
        self.assertEqual(self.draft(app,'component')[0]['Preço (R$)'],'13,123456789012')
        self.edit(app,'material',{1:{'Descrição':'Barra nova','Preço (R$)':'45,75','Unidade':'BAR','Comprimento barra (mm)':'6000'}})
        self.button(app,'+ Linha · Serviços externos').click().run()
        self.edit(app,'service',{0:{'Descrição':'Pintura','Preço (R$)':'20'}})
        self.assertEqual(self.saved,[])
        self.button(app,'Salvar tudo').click().run()
        self.assertEqual(len(app.exception),0)
        self.assertEqual(len(self.saved),1)
        payload=self.saved[0]
        prices={(kind,data['description']):data['price'] for kind,data in payload['changes']}
        self.assertEqual(prices,{('component','PARAFUSO'):'13.123456789012',('component','PORCA'):'3.50',('material','Barra nova'):'45.75',('service','Pintura'):'20'})
        self.assertEqual(payload['profiles'],[]);self.assertEqual(payload['version'],8)
        self.assertTrue(any('2 itens' in s.value for s in app.success))

    def test_navigation_and_technical_columns_keep_last_cell_and_hidden_precision(self):
        app=self.app()
        self.edit(app,'component',{0:{'Preço (R$)':'13'}});app.run()
        app.radio(key='test_route').set_value('Outra').run()
        app.radio(key='test_route').set_value('Central').run()
        self.assertEqual(self.draft(app,'component')[0]['Preço (R$)'],'13')
        self.edit(app,'material',{0:{'kg/m²':'9,123456789012','Preço (R$)':'26'}})
        next(c for c in app.checkbox if c.label=='Mostrar todos os campos').check().run()
        self.assertEqual(self.draft(app,'material')[0]['kg/m²'],'9,123456789012')
        next(c for c in app.checkbox if c.label=='Mostrar todos os campos').uncheck().run()
        self.button(app,'Salvar tudo').click().run()
        data=next(data for kind,data in self.saved[0]['changes'] if kind=='material')
        self.assertEqual(data['kg_m2'],'9.123456789012')

    def test_referenced_and_unknown_usage_cannot_be_removed_but_price_can_change(self):
        for usage in (2,None):
            with self.subTest(usage=usage):
                self.snapshot['bases']['component'][0]['usage_count']=usage
                app=self.app()
                self.edit(app,'component',{0:{'Selecionar':True,'Preço (R$)':'13'}});app.run()
                self.assertTrue(self.button(app,'Remover selecionados · Componentes').disabled)
                self.button(app,'Salvar tudo').click().run()
                self.assertEqual(self.saved[-1]['deletions'],[])
                self.assertEqual(self.saved[-1]['changes'][0][1]['price'],'13')

    def test_removing_free_row_keeps_other_row_edits_and_stages_deletion(self):
        app=self.app()
        self.edit(app,'component',{0:{'Preço (R$)':'13'},1:{'Selecionar':True}});app.run()
        self.button(app,'Remover selecionados · Componentes').click().run()
        self.assertEqual(len(self.grid(app,'component').value),1)
        self.assertEqual(self.grid(app,'component').value.iloc[0]['Código'],'PARAFUSO')
        self.assertEqual(self.saved,[])
        self.button(app,'Salvar tudo').click().run()
        self.assertEqual(self.saved[0]['deletions'],[('component',2)])
        self.assertEqual(self.saved[0]['changes'][0][1]['price'],'13')

    def test_pasted_rows_get_defaults_and_distinct_ids_without_double_add_on_rerun(self):
        app=self.app()
        self.edit(app,'process',added=[{'Descrição':'Corte','Preço (R$)':'80,125'},{'Descrição':'Dobra','Preço (R$)':'100'}]);app.run();app.run()
        self.button(app,'Salvar tudo').click().run()
        self.assertEqual(len(app.exception),0)
        self.assertEqual(len(self.saved[0]['changes']),2)
        rows=[data for kind,data in self.saved[0]['changes']]
        self.assertEqual([r['price'] for r in rows],['80.125','100'])
        self.assertTrue(all(r['unit']=='H' and r['active'] and r['factor']=='1' for r in rows))
        self.assertNotEqual(rows[0]['code'],rows[1]['code'])

    def test_validation_and_version_conflict_preserve_entire_draft(self):
        app=self.app()
        self.edit(app,'component',{0:{'Preço (R$)':'inválido'}})
        self.edit(app,'material',{0:{'Preço (R$)':'26'}})
        self.button(app,'Salvar tudo').click().run()
        self.assertEqual(self.saved,[]);self.assertTrue(app.error)
        self.assertEqual(self.draft(app,'component')[0]['Preço (R$)'],'inválido')
        self.assertEqual(self.draft(app,'material')[0]['Preço (R$)'],'26')
        self.edit(app,'component',{0:{'Preço (R$)':'13'}})
        self.failure=StalePreview('Os custos mudaram em outra sessão.')
        self.button(app,'Salvar tudo').click().run()
        self.assertEqual(self.saved,[]);self.assertTrue(app.error)
        self.assertEqual(self.draft(app,'component')[0]['Preço (R$)'],'13')
        self.assertEqual(self.draft(app,'material')[0]['Preço (R$)'],'26')

    def test_empty_lines_ignored_and_invalid_new_costs_do_not_reach_publish(self):
        app=self.app();self.button(app,'+ Linha · Componentes').click().run()
        self.button(app,'Salvar tudo').click().run();self.assertEqual(self.saved,[])
        for values in ({'Descrição':'Sem preço'},{'Descrição':'Zero','Preço (R$)':'0'},
                       {'Código':'PARAFUSO','Descrição':'Duplicado','Preço (R$)':'2'}):
            with self.subTest(values=values):
                app=self.app();self.edit(app,'component',added=[values])
                self.button(app,'Salvar tudo').click().run()
                self.assertEqual(self.saved,[]);self.assertTrue(app.error)

    def test_read_only_permission_cannot_include_remove_or_save(self):
        self.permissions={'view'};app=self.app()
        self.assertTrue(self.button(app,'Salvar tudo').disabled)
        self.assertTrue(all(b.disabled for b in app.button if b.label.startswith(('+ Linha','Remover selecionados'))))
        self.assertTrue(all(d.proto.disabled for d in app.dataframe))

    def test_reload_uses_new_workspace_and_does_not_reapply_old_deltas(self):
        app=self.app();self.edit(app,'component',{0:{'Preço (R$)':'13'}});app.run()
        self.snapshot['version']=9;self.snapshot['bases']['component'][0]['price']='14'
        self.button(app,'Recarregar valores salvos').click().run()
        self.assertEqual(self.grid(app,'component').value.iloc[0]['Preço (R$)'],'14')
        self.button(app,'Salvar tudo').click().run();self.assertEqual(self.saved,[])

    def test_date_rollover_preserves_unsaved_costs(self):
        from datetime import date
        with patch('pricing_catalog_ui._today',return_value=date(2026,11,8)) as today:
            app=self.app();self.edit(app,'component',{0:{'Preço (R$)':'13'}});app.run()
            today.return_value=date(2026,11,9);app.run()
            self.assertEqual(self.draft(app,'component')[0]['Preço (R$)'],'13')
            self.button(app,'Salvar tudo').click().run()
            self.assertEqual(self.saved[0]['changes'][0][1]['price'],'13')

    def test_permission_change_preserves_draft_and_disables_writes(self):
        app=self.app();self.edit(app,'component',{0:{'Preço (R$)':'13'}});app.run()
        self.permissions={'view'};app.run()
        self.assertTrue(self.button(app,'Salvar tudo').disabled)
        self.assertEqual(self.draft(app,'component')[0]['Preço (R$)'],'13')
        self.permissions={'view','costs'};app.run()
        self.button(app,'Salvar tudo').click().run()
        self.assertEqual(self.saved[0]['changes'][0][1]['price'],'13')
