import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
import pricing_items


class PricingScreensTests(unittest.TestCase):
    def test_switching_profile_does_not_reuse_another_profiles_unsaved_values(self):
        from pricing_repository import PricingRepository
        from pricing_service import PricingService
        profiles=[dict(id=i,code=name,reviewed_on='2026-11-06',data=dict(efficiency='1',taxes='0.3',rounding='CENT')) for i,name in [(1,'A'),(2,'B')]]
        with patch.object(PricingRepository,'list_profiles',return_value=profiles), \
             patch.object(PricingService,'preview_profile',return_value=dict(items=[],version=0,key='preview')):
            source='from pricing_ui import _profiles_tab\nfrom pricing_service import PricingService\ns=PricingService()\n_profiles_tab(s.repo,s,"admin",{"view","costs"},0)'
            app=AppTest.from_string(source,default_timeout=15).run()
            next(s for s in app.selectbox if s.label=='Perfil para editar').select('A').run()
            next(n for n in app.number_input if n.label=='Eficiência do perfil (%)').set_value(50)
            next(b for b in app.button if b.label=='Simular alteração do perfil').click().run()
            next(s for s in app.selectbox if s.label=='Perfil para editar').select('B').run()
            self.assertEqual(len(app.exception),0)
            self.assertEqual(next(n for n in app.number_input if n.label=='Eficiência do perfil (%)').value,100)
            self.assertFalse(any(b.label=='Salvar perfil e atualizar suas folhas' for b in app.button))

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
             patch.object(PricingRepository,'revisions',return_value=[]), \
             patch.object(PricingRepository,'list_bases',return_value=[]), \
             patch.object(PricingRepository,'list_profiles',return_value=[]), \
             patch.object(PricingRepository,'references',return_value=dict(version=0,items={})), \
             patch.object(PricingRepository,'events',return_value=[]):
            app=AppTest.from_string('from pricing_ui import render_pricing\nrender_pricing("editor")',default_timeout=15).run()
            self.assertEqual(len(app.exception),0)
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
