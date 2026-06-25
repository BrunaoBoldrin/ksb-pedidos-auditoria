"""Migra dados do antigo database.db (SQLite) para PostgreSQL/Supabase.

Uso local:
    python migrar_sqlite_para_postgres.py --sqlite database.db

O script usa as mesmas variáveis de ambiente do Render/Supabase:
DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD e, opcionalmente, DB_SSLMODE.
"""

import argparse
import sqlite3
from pathlib import Path

from database import conectar, inicializar_banco


TABELAS = {
    "materiais": [
        "id",
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
        "ativo",
        "data_cadastro",
        "data_atualizacao",
    ],
    "pedidos": [
        "id",
        "numero_pedido",
        "data_emissao",
        "comprador",
        "unidade",
        "data_upload",
        "arquivo_pdf",
        "status_etapa1",
        "status_etapa2",
    ],
    "pedido_itens": [
        "id",
        "pedido_id",
        "item_pedido",
        "codigo_material",
        "descricao",
        "quantidade",
        "unidade_medida",
        "data_entrega",
        "valor_unitario_pdf",
        "valor_total_pdf",
        "material",
        "norma",
        "ncm",
        "leadtime",
    ],
    "auditorias": [
        "id",
        "pedido_item_id",
        "data_auditoria",
        "etapa1_status",
        "etapa1_detalhes",
        "etapa2_status",
        "etapa2_detalhes",
        "preco_revisado",
        "preco_pdf",
        "diferenca",
    ],
    "regras_fiscais": [
        "id",
        "palavra_chave",
        "material",
        "ncm",
        "aliquota_icms",
        "aliquota_ipi",
        "observacao",
        "ativo",
    ],
}


def _sqlite_table_exists(cursor, tabela):
    cursor.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (tabela,))
    return cursor.fetchone() is not None


def _reset_sequence(pg_cursor, tabela):
    pg_cursor.execute(
        "SELECT setval(pg_get_serial_sequence(%s, 'id'), COALESCE((SELECT MAX(id) FROM " + tabela + "), 1), (SELECT COUNT(*) > 0 FROM " + tabela + "))",
        (tabela,),
    )


def migrar(sqlite_path, limpar_destino=False):
    sqlite_path = Path(sqlite_path)
    if not sqlite_path.exists():
        raise FileNotFoundError(f"Arquivo SQLite não encontrado: {sqlite_path}")

    inicializar_banco()

    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_cursor = sqlite_conn.cursor()
    pg_conn = conectar()

    try:
        pg_cursor = pg_conn.cursor()

        if limpar_destino:
            pg_cursor.execute(
                "TRUNCATE auditorias, pedido_itens, pedidos, regras_fiscais, materiais RESTART IDENTITY CASCADE"
            )

        totais = {}
        for tabela, colunas in TABELAS.items():
            if not _sqlite_table_exists(sqlite_cursor, tabela):
                totais[tabela] = 0
                continue

            sqlite_cursor.execute(f"SELECT {', '.join(colunas)} FROM {tabela}")
            linhas = sqlite_cursor.fetchall()
            totais[tabela] = len(linhas)

            if not linhas:
                continue

            placeholders = ", ".join(["%s"] * len(colunas))
            update_cols = [col for col in colunas if col != "id"]
            update_sql = ", ".join([f"{col} = EXCLUDED.{col}" for col in update_cols])
            insert_sql = (
                f"INSERT INTO {tabela} ({', '.join(colunas)}) VALUES ({placeholders}) "
                f"ON CONFLICT (id) DO UPDATE SET {update_sql}"
            )
            pg_cursor.executemany(insert_sql, linhas)
            _reset_sequence(pg_cursor, tabela)

        pg_conn.commit()
        return totais
    except Exception:
        pg_conn.rollback()
        raise
    finally:
        pg_conn.close()
        sqlite_conn.close()


def main():
    parser = argparse.ArgumentParser(description="Migra dados do SQLite para PostgreSQL/Supabase.")
    parser.add_argument("--sqlite", default="database.db", help="Caminho do arquivo SQLite de origem.")
    parser.add_argument(
        "--limpar-destino",
        action="store_true",
        help="Remove dados existentes no PostgreSQL antes de importar.",
    )
    args = parser.parse_args()

    totais = migrar(args.sqlite, limpar_destino=args.limpar_destino)
    for tabela, total in totais.items():
        print(f"{tabela}: {total} registro(s) migrado(s)")


if __name__ == "__main__":
    main()
