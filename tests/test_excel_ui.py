"""Exercise reference-sheet edits through the real form and formula engine."""
import unittest
from copy import deepcopy

from streamlit.testing.v1 import AppTest
from pricing_excel import recalculate
from pricing_service import StalePreview


def model():
    def cell(value=None,formula=None,kind='number',label='',section='Materiais'):
        return dict(value=value,formula=formula,cached='9999' if formula else value,
                    editable=not formula,external=False,input_type=kind,label=label,section=section)
    return dict(format_version=1,sheet_name='Fonte',max_row=6,max_column=2,warnings=[],sections=[],
        cells={'A1':cell('10',label='Preço por kg'),'A2':cell('2',label='Consumo'),
               'A3':cell(formula='=A1*A2'),'A4':cell(formula='=A3*2'),
               'A5':cell('2',label='Quantidade da fonte',section='Identificação'),
               'A6':cell(formula='=A4/A5'),
               'B1':cell('',kind='text',label='Fornecedor',section='Serviços externos')},
        outputs=dict(cost='A3',gross='A4',pieces='A5',unit_price='A6',breakdown={'material':'A3'}))


class SourceStore:
    def __init__(self):
        self.row=dict(id=1,filename='Fonte.xlsx',sha256='a'*64,linked_codes=[],version=1,
                      author='admin',updated_at='2026-11-09',model=model(),edits={})
        self.fail=False
    def list_sources(self,actor):return [{k:v for k,v in self.row.items() if k not in ('model','edits')}]
    def get_source(self,source_id,actor):return deepcopy(self.row)
    def save_inputs(self,source_id,edits,actor,expected_version):
        if self.fail:raise StalePreview('A fonte foi alterada por outro usuário.')
        if expected_version!=self.row['version']:raise StalePreview('Conflito')
        recalculate(self.row['model'],edits)
        self.row['edits']=deepcopy(edits);self.row['version']+=1
        return deepcopy(self.row)


class ExcelSourceScreenTests(unittest.TestCase):
    def app(self,permissions=None):
        self.store=SourceStore()
        app=AppTest.from_string('import streamlit as st\nfrom pricing_excel_ui import render_excel_sources\npage=st.radio("Tela",["Conferência","Outra"],key="qa_route")\nif page=="Conferência":render_excel_sources("admin",st.session_state.qa_store,st.session_state.qa_permissions)',default_timeout=20)
        app.session_state.qa_store=self.store
        app.session_state.qa_permissions=permissions if permissions is not None else {'view','edit','costs'}
        app.run()
        self.assertEqual(len(app.exception),0)
        app.session_state['excel_sources_table']={'edited_rows':{0:{'Selecionar':True}},'added_rows':[],'deleted_rows':[]}
        next(b for b in app.button if b.label=='Abrir planilha selecionada').click().run()
        self.assertEqual(len(app.exception),0)
        return app

    def edit(self,app,address,value):
        for grid in app.dataframe:
            if str(grid.key).startswith('excel_inputs_'):
                indexes=grid.value.index[grid.value['Célula']==address].tolist()
                if indexes:
                    app.session_state[grid.key]={'edited_rows':{indexes[0]:{'Valor':value}},'added_rows':[],'deleted_rows':[]}
                    return
        self.fail('Campo de entrada ausente: '+address)

    def test_all_inputs_include_blank_supplier_and_formulas_remain_read_only(self):
        app=self.app()
        addresses=[a for grid in app.dataframe if str(grid.key).startswith('excel_inputs_') for a in grid.value['Célula']]
        self.assertEqual(set(addresses),{'A1','A2','A5','B1'})
        self.assertEqual(next(m for m in app.metric if m.label=='PV original por peça').value,'R$ 20,00')

    def test_edit_recalculates_formula_and_save_preserves_other_sections(self):
        app=self.app();self.edit(app,'A1','15,00');self.edit(app,'B1','Pintura Azul')
        next(b for b in app.button if b.label=='Recalcular conferência').click().run()
        self.assertEqual(len(app.exception),0)
        self.assertEqual(next(m for m in app.metric if m.label=='PV por peça desta edição').value,'R$ 30,00')
        self.assertEqual(self.store.row['edits'],{})
        next(b for b in app.button if b.label=='Salvar conferência').click().run()
        self.assertEqual(len(app.exception),0)
        self.assertEqual(self.store.row['edits']['B1'],'Pintura Azul')
        self.assertEqual(recalculate(self.store.row['model'],self.store.row['edits'])['gross_per_piece'],'30')

    def test_invalid_cell_and_conflict_keep_draft_without_saving(self):
        app=self.app();self.edit(app,'A1','inválido')
        next(b for b in app.button if b.label=='Salvar conferência').click().run()
        self.assertTrue(app.error);self.assertEqual(self.store.row['edits'],{})
        self.edit(app,'A1','17');self.store.fail=True
        next(b for b in app.button if b.label=='Salvar conferência').click().run()
        self.assertTrue(app.error);self.assertEqual(self.store.row['edits'],{})
        self.store.fail=False
        next(b for b in app.button if b.label=='Salvar conferência').click().run()
        self.assertEqual(self.store.row['edits']['A1'],'17')

    def test_viewer_cannot_edit_or_save(self):
        app=self.app({'view'})
        self.assertTrue(next(b for b in app.button if b.label=='Salvar conferência').disabled)
        self.assertTrue(all(grid.proto.disabled for grid in app.dataframe if str(grid.key).startswith('excel_inputs_')))

    def test_recalculated_inputs_survive_navigation_with_matching_results(self):
        app=self.app();self.edit(app,'A1','15')
        next(b for b in app.button if b.label=='Recalcular conferência').click().run()
        app.radio(key='qa_route').set_value('Outra').run()
        app.radio(key='qa_route').set_value('Conferência').run()
        grid=next(g for g in app.dataframe if str(g.key).startswith('excel_inputs_') and 'A1' in list(g.value['Célula']))
        self.assertEqual(grid.value.loc[grid.value['Célula']=='A1','Valor'].iloc[0],'15')
        self.assertEqual(next(m for m in app.metric if m.label=='PV por peça desta edição').value,'R$ 30,00')
