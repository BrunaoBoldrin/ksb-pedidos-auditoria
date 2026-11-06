import unittest
from io import BytesIO
from unittest.mock import patch
import pandas as pd

import pricing_items


class TechnicalImportTests(unittest.TestCase):
    def test_old_price_columns_are_ignored_and_codes_remain_text(self):
        source=pd.DataFrame({'Código Material':['00123'],'Descrição':['Teste'],
                             'Preço Unitário Líquido':['valor inválido'], 'Última Revisão':['antiga']})
        with patch.object(pd,'read_excel',return_value={'Itens':source}):
            result,notes=pricing_items.import_items(BytesIO())
        self.assertEqual(result.iloc[0]['Código Material'],'00123')
        self.assertEqual(list(result.columns),pricing_items.COLUMNS)
        self.assertTrue(any('ignoradas' in n for n in notes))


if __name__=='__main__':unittest.main()
