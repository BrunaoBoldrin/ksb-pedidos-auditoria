import copy
import unittest
from datetime import date

from pricing_workspace import new_workspace, workspace_changes


class WorkspaceTests(unittest.TestCase):
    def snapshot(self):
        def base(id,code,price):
            return dict(id=id,code=code,description=code,unit='UN',price=price,factor='1.000000000000',kg_m2=None,length_mm=None,
                        per_person=True,reviewed_on='2026-11-01',active=True,version=2,note='')
        return dict(version=8,bases=dict(component=[base(1,'PARAFUSO','10.123456789012'),base(2,'PORCA','2.000000000000')],material=[],process=[],service=[]),
                    profiles=[dict(id=1,code='GERAL',data=dict(efficiency='0.65',taxes='0.3',rounding='CENT'),reviewed_on='2026-11-01',active=True,version=3)])

    def test_multiple_cost_and_profile_edits_keep_source_version_and_full_precision(self):
        workspace=new_workspace(self.snapshot())
        costs=copy.deepcopy(workspace['costs']);profiles=copy.deepcopy(workspace['profiles'])
        self.assertEqual(workspace_changes(workspace,costs,profiles,date(2026,11,6)),([],[],[]))
        costs[0]['Preço (R$)']='13.123456789012'
        costs[1]['Preço (R$)']='3,50'
        profiles[0]['Impostos (%)']='20'
        changes,profile_changes,deleted=workspace_changes(workspace,costs,profiles,date(2026,11,6))
        self.assertEqual(workspace['version'],8)
        self.assertEqual([r['price'] for _,r in changes],['13.123456789012','3.50'])
        self.assertTrue(all(r['reviewed_on']=='2026-11-06' for _,r in changes))
        self.assertEqual(profile_changes[0]['data']['taxes'],'0.2')
        self.assertEqual(deleted,[])
        self.assertEqual(workspace['originals']['component:1']['price'],'10.123456789012')

    def test_cost_category_is_stable_and_deletion_retains_server_identity(self):
        workspace=new_workspace(self.snapshot())
        costs=copy.deepcopy(workspace['costs'])
        costs[0]['Categoria']='Matérias-primas'
        with self.assertRaises(ValueError):workspace_changes(workspace,costs,workspace['profiles'],date(2026,11,6))
        workspace['deleted']=[('component',1)]
        self.assertEqual(workspace_changes(workspace,workspace['costs'][1:],workspace['profiles'],date(2026,11,6))[2],[('component',1)])
