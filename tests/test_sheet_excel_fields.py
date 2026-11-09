import unittest
from copy import deepcopy
from datetime import date
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from pricing_sheet_data import sheet_rows, composition_from_rows


class ExcelFieldTests(unittest.TestCase):
    def test_line_metadata_and_unexposed_source_fields_survive_edit(self):
        base=dict(id=1,code='A',description='Peça',unit='UN',price='10',version=1)
        catalog=dict(material=[],component=[base],process=[],service=[dict(base,id=2)])
        original=dict(kind='component',base_id=1,position='7',supplier='Fornecedor original',source_cell='D19',legacy_conversion={'denominator':'6000'})
        rows=sheet_rows(dict(lines=[original]),catalog)
        self.assertEqual(rows['component'][0]['Posição'],'7')
        rows['component'][0]['Fornecedor']='Fornecedor novo'
        lines,proposals=composition_from_rows(rows,catalog,date(2026,11,9))
        self.assertEqual(lines[0]['supplier'],'Fornecedor novo')
        self.assertEqual(lines[0]['source_cell'],'D19')
        self.assertEqual(lines[0]['legacy_conversion'],{'denominator':'6000'})
        self.assertEqual(proposals,[])

    def test_edit_header_supplier_operation_and_tooling_preserves_source_evidence(self):
        from pricing_repository import PricingRepository
        from pricing_catalog import CatalogService
        base=dict(id=1,code='LASER',description='Laser',unit='UN',price='10',factor='1',active=True,version=1,reviewed_on='2026-11-06')
        data=dict(customer='KSB',seller='Karina',product='Desenho X',quote_type='integral',
                  lines=[dict(kind='service',base_id=1,position='2',supplier='Fornecedor A',operation_code='OP-1',source_cell='E43')],
                  tooling=[dict(description='Matriz',annual_quantity='1200',cost='450',amortization_quantity='100')],
                  tool_cost='0',margin='0.2',efficiency='1',commission='0',rounding='CENT',reviewed_on='2026-11-06',
                  import_source_sha256='abc',import_historical={'pv':99},future_metadata={'keep':True})
        row=dict(revision_id=1,number=1,status='DRAFT',material_code='001',descricao='Teste',data=data)
        snapshot=dict(version=8,bases=dict(material=[],component=[],process=[],service=[base]),profiles=[])
        sent=[]
        def save(code,params,actor,version):sent.append(deepcopy(params));return dict(id=2,number=2)
        with patch.object(PricingRepository,'catalog',return_value=snapshot),patch.object(PricingRepository,'version',return_value=8), \
             patch.object(PricingRepository,'sheets',return_value=[row]),patch.object(CatalogService,'permissions',return_value={'view','edit','costs'}), \
             patch.object(CatalogService,'preview_draft',side_effect=ValueError('Fixture')),patch.object(CatalogService,'save_draft',side_effect=save):
            app=AppTest.from_string('from pricing_sheets_ui import render_sheets\nrender_sheets("admin")',default_timeout=20).run()
            app.session_state['pricing_sheets_table']={'edited_rows':{0:{'Selecionar':True}},'added_rows':[],'deleted_rows':[]}
            app.run();next(b for b in app.button if b.label=='Editar folha').click().run()
            self.assertFalse(app.exception)
            next(t for t in app.text_input if t.label=='Vendedor').set_value('Bruno')
            service=next(d for d in app.dataframe if '_service_' in str(d.key))
            app.session_state[service.key]={'edited_rows':{0:{'Fornecedor':'Fornecedor B','Código operação':'OP-2'}},'added_rows':[],'deleted_rows':[]}
            tool=next(d for d in app.dataframe if '_tooling' in str(d.key))
            app.session_state[tool.key]={'edited_rows':{0:{'Custo total (R$)':'600,50','Quantidade para amortização':'200'}},'added_rows':[],'deleted_rows':[]}
            next(b for b in app.button if b.label=='Salvar rascunho').click().run()
            self.assertFalse(app.exception)
            result=sent[0]
            self.assertEqual(result['seller'],'Bruno')
            self.assertEqual(result['customer'],'KSB')
            self.assertEqual(result['product'],'Desenho X')
            self.assertEqual(result['quote_type'],'integral')
            self.assertEqual(result['tooling'],[dict(description='Matriz',annual_quantity='1200',cost='600.50',amortization_quantity='200')])
            self.assertEqual(result['lines'][0]['supplier'],'Fornecedor B')
            self.assertEqual(result['lines'][0]['operation_code'],'OP-2')
            self.assertEqual(result['lines'][0]['source_cell'],'E43')
            self.assertEqual(result['import_source_sha256'],'abc')
            self.assertEqual(result['import_historical'],{'pv':99})
            self.assertEqual(result['future_metadata'],{'keep':True})

    def test_tooling_missing_amortization_is_not_silently_accepted(self):
        from pricing_sheet_data import tooling_from_rows
        with self.assertRaises(ValueError):tooling_from_rows([{'Descrição':'Ferramenta','Custo total (R$)':'500','Quantidade para amortização':''}])
        self.assertEqual(tooling_from_rows([{'Descrição':'','Custo total (R$)':'','Quantidade para amortização':''}]),[])

    def test_tooling_numeric_zero_round_trip_is_distinct_from_blank(self):
        from pricing_sheet_data import tooling_rows, tooling_from_rows
        data={'tooling':[dict(description='Ferramenta sem custo',annual_quantity=0,cost=0,amortization_quantity=1)]}
        rows=tooling_rows(data)
        self.assertEqual(rows[0]['Custo total (R$)'],'0')
        self.assertEqual(rows[0]['Quantidade anual'],'0')
        self.assertEqual(tooling_from_rows(rows),[dict(description='Ferramenta sem custo',annual_quantity='0',cost='0',amortization_quantity='1')])
