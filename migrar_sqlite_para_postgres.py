"""Migra dados do antigo database.db (SQLite) para PostgreSQL/Neon.

Uso via GitHub Actions:
    Actions -> Migrar SQLite para PostgreSQL -> Run workflow

Uso local:
    python migrar_sqlite_para_postgres.py --sqlite database.db

O script usa as mesmas variáveis de ambiente do Render/Neon:
DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD e, opcionalmente, DB_SSLMODE.
"""

import argparse
import sqlite3
from pathlib import Path

from database import conectar, inicializar_banco


SQLITE_DB_PADRAO = "database.db"


def tabela_existe(cursor, tabela):
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (tabela,),
    )
    return cursor.fetchone() is not None


def colunas_sqlite(cursor, tabela):
    cursor.execute(f"PRAGMA table_info({tabela})")
    return [linha[1] for linha in cursor.fetchall()]


def selecionar_colunas_existentes(cursor, tabela, colunas):
    existentes = set(colunas_sqlite(cursor, tabela))
    return [coluna for coluna in colunas if coluna in existentes]


def resetar_sequence(pg_cursor, tabela):
    pg_cursor.execute(
        """
        SELECT pg_get_serial_sequence(%s, 'id')
        """,
        (tabela,),
    )
    sequence = pg_cursor.fetchone()[0]

    if not sequence:
        return

    pg_cursor.execute(
        f"""
        SELECT COALESCE(MAX(id), 1), COUNT(*) > 0
        FROM {tabela}
        """
    )
    max_id, possui_dados = pg_cursor.fetchone()

    pg_cursor.execute(
        "SELECT setval(%s, %s, %s)",
        (sequence, max_id, possui_dados),
    )


def migrar_materiais(sqlite_cursor, pg_cursor):
    tabela = "materiais"

    if not tabela_existe(sqlite_cursor, tabela):
        return 0

    colunas = selecionar_colunas_existentes(
        sqlite_cursor,
        tabela,
        [
            "codigo_material",
            "descricao",
            "material",
            "norma",
            "ncm",
            "unidade_medida",
            "codigo_interno_jundiai",
            "codigo_interno_varzea",
            "preco_revisado",
            "data_ultima_revisao",
        ],
    )

    if not colunas:
        return 0

    sqlite_cursor.execute(f"SELECT {', '.join(colunas)} FROM {tabela}")
    linhas = sqlite_cursor.fetchall()

    if not linhas:
        return 0

    placeholders = ", ".join(["%s"] * len(colunas))
    updates = ", ".join([
        f"{coluna} = EXCLUDED.{coluna}"
        for coluna in colunas
        if coluna != "codigo_material"
    ])

    sql = f"""
        INSERT INTO materiais ({', '.join(colunas)})
        VALUES ({placeholders})
        ON CONFLICT (codigo_material) DO UPDATE SET
            {updates}
    """

    pg_cursor.executemany(sql, linhas)

    return len(linhas)


def migrar_regras_fiscais(sqlite_cursor, pg_cursor):
    tabela = "regras_fiscais"

    if not tabela_existe(sqlite_cursor, tabela):
        return 0

    colunas = selecionar_colunas_existentes(
        sqlite_cursor,
        tabela,
        [
            "id",
            "palavra_chave",
            "material",
            "ncm",
            "aliquota_icms",
            "aliquota_ipi",
            "observacao",
            "ativo",
        ],
    )

    if not colunas:
        return 0

    sqlite_cursor.execute(f"SELECT {', '.join(colunas)} FROM {tabela}")
    linhas = sqlite_cursor.fetchall()

    if not linhas:
        return 0

    placeholders = ", ".join(["%s"] * len(colunas))

    if "id" in colunas:
        updates = ", ".join([
            f"{coluna} = EXCLUDED.{coluna}"
            for coluna in colunas
            if coluna != "id"
        ])
        conflito = f"ON CONFLICT (id) DO UPDATE SET {updates}"
    else:
        conflito = ""

    sql = f"""
        INSERT INTO regras_fiscais ({', '.join(colunas)})
        VALUES ({placeholders})
        {conflito}
    """

    pg_cursor.executemany(sql, linhas)
    resetar_sequence(pg_cursor, tabela)

    return len(linhas)


def migrar_usuarios(sqlite_cursor, pg_cursor):
    tabela = "usuarios"

    if not tabela_existe(sqlite_cursor, tabela):
        return 0

    colunas = selecionar_colunas_existentes(
        sqlite_cursor,
        tabela,
        [
            "id",
            "nome",
            "usuario",
            "senha",
            "perfil",
            "ativo",
        ],
    )

    if not colunas or "usuario" not in colunas:
        return 0

    sqlite_cursor.execute(f"SELECT {', '.join(colunas)} FROM {tabela}")
    linhas = sqlite_cursor.fetchall()

    if not linhas:
        return 0

    placeholders = ", ".join(["%s"] * len(colunas))
    updates = ", ".join([
        f"{coluna} = EXCLUDED.{coluna}"
        for coluna in colunas
        if coluna != "usuario"
    ])

    sql = f"""
        INSERT INTO usuarios ({', '.join(colunas)})
        VALUES ({placeholders})
        ON CONFLICT (usuario) DO UPDATE SET
            {updates}
    """

    pg_cursor.executemany(sql, linhas)
    resetar_sequence(pg_cursor, tabela)

    return len(linhas)


def limpar_destino(pg_cursor):
    pg_cursor.execute(
        """
        TRUNCATE TABLE
            regras_fiscais,
            materiais,
            usuarios
        RESTART IDENTITY CASCADE
        """
    )


def migrar(sqlite_path=SQLITE_DB_PADRAO, limpar=False):
    sqlite_path = Path(sqlite_path)

    if not sqlite_path.exists():
        raise FileNotFoundError(f"Arquivo SQLite não encontrado: {sqlite_path}")

    inicializar_banco()

    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_cursor = sqlite_conn.cursor()

    pg_conn = conectar()
    pg_cursor = pg_conn.cursor()

    try:
        if limpar:
            limpar_destino(pg_cursor)

        totais = {
            "materiais": migrar_materiais(sqlite_cursor, pg_cursor),
            "regras_fiscais": migrar_regras_fiscais(sqlite_cursor, pg_cursor),
            "usuarios": migrar_usuarios(sqlite_cursor, pg_cursor),
        }

        pg_conn.commit()
        return totais

    except Exception:
        pg_conn.rollback()
        raise

    finally:
        pg_cursor.close()
        pg_conn.close()
        sqlite_conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Migra dados do SQLite para PostgreSQL/Neon."
    )
    parser.add_argument(
        "--sqlite",
        default=SQLITE_DB_PADRAO,
        help="Caminho do arquivo SQLite de origem.",
    )
    parser.add_argument(
        "--limpar-destino",
        action="store_true",
        help="Apaga dados atuais do PostgreSQL antes de importar.",
    )

    args = parser.parse_args()

    totais = migrar(
        sqlite_path=args.sqlite,
        limpar=args.limpar_destino,
    )

    print("Migração concluída.")
    for tabela, total in totais.items():
        print(f"{tabela}: {total} registro(s) migrado(s)")


if __name__ == "__main__":
    main()
