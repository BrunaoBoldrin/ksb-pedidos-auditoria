import unittest
from unittest.mock import patch
from types import SimpleNamespace

import database


class WireConnection:
    def __init__(self):
        self.closed=False;self.rollbacks=0;self.info=SimpleNamespace(transaction_status=0)
    def close(self):self.closed=True
    def rollback(self):self.rollbacks+=1;self.info.transaction_status=0
    def commit(self):self.info.transaction_status=0
    def __enter__(self):return self
    def __exit__(self,*args):self.rollback() if args[0] else self.commit()


class DatabasePoolTests(unittest.TestCase):
    def test_connections_are_reused_and_uncommitted_work_cannot_leak(self):
        wires=[]
        def create(**kwargs):
            wire=WireConnection();wires.append(wire);return wire
        with patch.object(database,'_get_db_config',return_value={'host':'fixture-reuse'}),patch('psycopg2.connect',side_effect=create):
            first=database.conectar()
            wires[0].info.transaction_status=2
            first.close();first.close()
            second=database.conectar()
            self.assertEqual(len(wires),1,'Abrir outra tela deve reutilizar a conexão')
            self.assertEqual(wires[0].rollbacks,1,'Transação anterior precisa terminar antes do próximo usuário')
            second.close()

    def test_concurrent_borrowers_and_database_targets_are_isolated(self):
        wires=[]
        def create(**kwargs):
            wire=WireConnection();wires.append(wire);return wire
        with patch('psycopg2.connect',side_effect=create):
            with patch.object(database,'_get_db_config',return_value={'host':'fixture-one'}):
                a=database.conectar();b=database.conectar()
            with patch.object(database,'_get_db_config',return_value={'host':'fixture-two'}):c=database.conectar()
            self.assertEqual(len(wires),3)
            a.close();b.close();c.close()

    def test_failed_transaction_releases_connection_without_replaying_write(self):
        wires=[]
        def create(**kwargs):
            wire=WireConnection();wires.append(wire);return wire
        with patch.object(database,'_get_db_config',return_value={'host':'fixture-error'}),patch('psycopg2.connect',side_effect=create):
            conn=database.conectar()
            with self.assertRaisesRegex(ValueError,'write failed'):
                with conn:raise ValueError('write failed')
            conn.close()
            next_conn=database.conectar()
            self.assertEqual(len(wires),1)
            self.assertEqual(wires[0].rollbacks,1)
            next_conn.close()
