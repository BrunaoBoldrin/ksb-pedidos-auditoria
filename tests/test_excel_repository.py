"""Imported Excel inputs persist independently of commercial price publications."""
import os
import unittest

import test_pricing_repository as repository_fixture


def source_model():
    def cell(value, formula=None, kind='number'):
        return dict(value=value, cached=value, formula=formula, editable=formula is None,
                    external=False, input_type=kind, label='Campo', section='Teste')
    return dict(format_version=1, sheet_name='Teste', cells={
        'A1':cell('10'), 'A2':cell('2'), 'A3':cell('20','=A1*A2'),
        'A4':cell('40','=A3*2'), 'A5':cell('2'), 'A6':cell('20','=A4/A5'),
        'B1':cell('Fornecedor',kind='text'),
    }, outputs=dict(cost='A3',gross='A4',unit_price='A6',pieces='A5'), sections=['Teste'], warnings=[])

@unittest.skipUnless(os.environ.get('PRICING_TEST_DSN'), 'PostgreSQL de teste não configurado')
class ExcelRepositoryTests(unittest.TestCase):
    # Reuse the isolated schema setup, without inheriting/re-running its test cases.
    setUp = repository_fixture.RepositoryTests.setUp
    tearDown = repository_fixture.RepositoryTests.tearDown

    def source_service(self):
        from pricing_excel_service import ExcelSourceService
        return ExcelSourceService(self.repo)

    model = staticmethod(source_model)

    def create(self, **kwargs):
        return self.source_service().import_source(self.model(),'Teste.xlsx','a'*64,['A'],'admin',**kwargs)

    def test_import_is_idempotent_and_does_not_overwrite_saved_inputs(self):
        service=self.source_service();version=self.repo.version()
        created=self.create()
        self.assertEqual(created['version'],1)
        saved=service.save_inputs(created['id'],{'A1':'13,25','B1':'Novo fornecedor'},'admin',1)
        self.assertEqual(saved['version'],2)
        duplicate=self.create()
        self.assertEqual(duplicate['id'],created['id'])
        self.assertEqual(duplicate['edits'],saved['edits'])
        self.assertEqual(duplicate['model'],created['model'])
        summary=service.list_sources('admin')
        self.assertEqual(len(summary),1)
        self.assertNotIn('model',summary[0]);self.assertNotIn('edits',summary[0])
        self.assertEqual(service.get_source(created['id'],'admin')['linked_codes'],['A'])
        self.assertEqual(self.repo.version(),version)
        with self.repo.transaction() as c:
            c.execute('SELECT count(*) AS n FROM pricing_prices');self.assertEqual(c.fetchone()['n'],0)
            c.execute("SELECT action,data FROM pricing_events WHERE action LIKE 'PLANILHA EXCEL%' ORDER BY id")
            events=c.fetchall()
        self.assertEqual(len(events),2)
        self.assertEqual(events[-1]['data']['before'],{})
        self.assertEqual(events[-1]['data']['after'],saved['edits'])

    def test_stale_save_rolls_back_and_keeps_original_model_immutable(self):
        from pricing_service import StalePreview
        service=self.source_service();row=self.create()
        service.save_inputs(row['id'],{'A1':'20'},'admin',1)
        with self.assertRaises(StalePreview):service.save_inputs(row['id'],{'A1':'30'},'admin',1)
        current=service.get_source(row['id'],'admin')
        self.assertEqual(current['edits'],{'A1':'20'})
        self.assertEqual(current['model'],row['model'])

    def test_invalid_edit_or_broken_output_is_not_saved(self):
        service=self.source_service();row=self.create()
        for edits in ({'A3':'1'},{'Z99':'1'},{'A1':'NaN'},{'A1':'Infinity'},{'A5':'0'}):
            with self.subTest(edits=edits):
                with self.assertRaises(ValueError):service.save_inputs(row['id'],edits,'admin',1)
                self.assertEqual(service.get_source(row['id'],'admin')['version'],1)
                self.assertEqual(service.get_source(row['id'],'admin')['edits'],{})

    def test_unknown_item_or_invalid_file_hash_cannot_be_imported(self):
        service=self.source_service()
        with self.assertRaises(ValueError):service.import_source(self.model(),'Teste.xlsx','a'*64,['INVENTADO'],'admin')
        with self.assertRaises(ValueError):service.import_source(self.model(),'Teste.xlsx','invalid',[],'admin')
        self.assertEqual(service.list_sources('admin'),[])

    def test_readers_cannot_change_inputs_and_cost_permission_alone_is_insufficient(self):
        service=self.source_service();row=self.create()
        with self.assertRaises(PermissionError):service.get_source(row['id'],'venda')
        self.service.set_permissions('venda',['view'],'admin',self.repo.version())
        self.assertEqual(service.get_source(row['id'],'venda')['id'],row['id'])
        with self.assertRaises(PermissionError):service.save_inputs(row['id'],{'A1':'20'},'venda',1)
        with self.assertRaises(PermissionError):service.import_source(self.model(),'Teste.xlsx','b'*64,[],'venda')
        self.service.set_permissions('venda',['view','costs'],'admin',self.repo.version())
        with self.assertRaises(PermissionError):service.save_inputs(row['id'],{'A1':'20'},'venda',1)
        self.service.set_permissions('venda',['view','costs','edit'],'admin',self.repo.version())
        self.assertEqual(service.save_inputs(row['id'],{'A1':'20'},'venda',1)['version'],2)


class ExcelSourceValidationTests(unittest.TestCase):
    def test_model_must_have_bounded_cells_and_required_outputs(self):
        from pricing_excel_service import validate_model
        for model in ({}, {'format_version':1,'cells':[], 'outputs':{}},
                      {'format_version':1,'cells':{'A1':{}},'outputs':{}},
                      {'format_version':1,'cells':{str(i):{} for i in range(5001)},'outputs':{}}):
            with self.subTest(model_type=str(type(model))):
                with self.assertRaises(ValueError):validate_model(model)

    def test_hash_and_link_identifiers_are_normalized_without_inventing_codes(self):
        from pricing_excel_service import normalize_identity
        filename,digest,codes=normalize_identity(' Teste.xlsx ','A'*64,['A',' A ','B'])
        self.assertEqual((filename,digest,codes),('Teste.xlsx','a'*64,['A','B']))
        for args in (('', 'a'*64,[]), ('Teste.xlsx','bad',[]), ('Teste.xlsx','a'*64,'A')):
            with self.subTest(args=args):
                with self.assertRaises(ValueError):normalize_identity(*args)

    def test_inputs_are_recalculated_and_invalid_totals_cannot_be_saved(self):
        from pricing_excel_service import _validated_inputs
        model=source_model()
        edits={'A1':'13,25','B1':'Fornecedor novo'}
        self.assertEqual(_validated_inputs(model,edits),edits)
        self.assertEqual(model['cells']['A1']['value'],'10')
        for bad in ({'A3':'10'},{'Z99':'1'},{'A1':'NaN'},{'A5':'0'},{'A1':'-100'}):
            with self.subTest(edits=bad):
                with self.assertRaises(ValueError):_validated_inputs(model,bad)
