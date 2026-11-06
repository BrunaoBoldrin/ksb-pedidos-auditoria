"""The publication lock must precede the final permission check."""
import unittest
from contextlib import contextmanager

from pricing_service import PricingService


class PricingPermissionTests(unittest.TestCase):
    def test_permission_revoked_while_waiting_for_lock_blocks_preview(self):
        class Cursor:
            locked = False
            def execute(self, query, params=None):
                if 'FOR UPDATE' in query:
                    self.locked = True  # another transaction revoked this user before releasing the lock
                self.query = query
            def fetchone(self):
                if 'FROM usuarios' in self.query:
                    return dict(perfil='VENDEDORA', ativo=0 if self.locked else 1, permissions=['view','costs'])
                return dict(version=0)
        class Repo:
            @contextmanager
            def transaction(self):yield Cursor()
        with self.assertRaises(PermissionError):
            PricingService(Repo()).preview_costs([], 'venda')


if __name__ == '__main__':unittest.main()
