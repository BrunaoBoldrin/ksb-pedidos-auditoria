"""Bounded PostgreSQL connections; each lease owns its entire transaction."""
import atexit
import threading
import time
from functools import lru_cache

import psycopg2
from psycopg2 import extensions
from psycopg2.pool import ThreadedConnectionPool

_creation_lock=threading.Lock()


class ConnectionPool:
    def __init__(self,config):
        self.pool=ThreadedConnectionPool(1,8,**config)
        self.slots=threading.BoundedSemaphore(8)
        self.returned={}
        atexit.register(self.pool.closeall)

    def acquire(self):
        if not self.slots.acquire(timeout=10):
            raise psycopg2.OperationalError('Banco ocupado. Tente novamente em instantes.')
        connection=None
        try:
            connection=self.pool.getconn()
            idle=time.monotonic()-self.returned.pop(id(connection),time.monotonic())
            if connection.closed or idle>30:
                try:
                    with connection.cursor() as cursor:cursor.execute('SELECT 1')
                    connection.rollback()
                except psycopg2.Error:
                    self.pool.putconn(connection,close=True)
                    connection=None
                    connection=self.pool.getconn()
            return ConnectionLease(self,connection)
        except Exception:
            if connection is not None:self.pool.putconn(connection,close=True)
            self.slots.release()
            raise

    def release(self,connection):
        discard=bool(connection.closed)
        try:
            if not discard and connection.info.transaction_status!=extensions.TRANSACTION_STATUS_IDLE:
                try:connection.rollback()
                except psycopg2.Error:discard=True
            self.pool.putconn(connection,close=discard)
            if not connection.closed:self.returned[id(connection)]=time.monotonic()
        finally:self.slots.release()


class ConnectionLease:
    def __init__(self,owner,connection):
        self._owner=owner;self._connection=connection;self._released=False

    @property
    def closed(self):return self._released or self._connection.closed

    def __getattr__(self,name):
        if self._released:raise psycopg2.InterfaceError('Conexão já devolvida ao pool.')
        return getattr(self._connection,name)

    def __enter__(self):
        if self._released:raise psycopg2.InterfaceError('Conexão já devolvida ao pool.')
        self._connection.__enter__()
        return self

    def __exit__(self,*args):return self._connection.__exit__(*args)

    def close(self):
        if not self._released:
            self._released=True
            self._owner.release(self._connection)


@lru_cache(maxsize=4)
def _pool(config):return ConnectionPool(dict(config))


def connect(config):
    # Credentials/endpoint are part of the key, so test and production never share a pool.
    with _creation_lock:pool=_pool(tuple(sorted(config.items())))
    return pool.acquire()
