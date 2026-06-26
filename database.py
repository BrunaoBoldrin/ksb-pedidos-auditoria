"""Camada de acesso a dados PostgreSQL/Neon.

Mantém as funções públicas usadas pelo app.py e parser.py.
"""

import os
from contextlib import contextmanager

import psycopg2


_REQUIRED_ENV_VARS = ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD")


def _get_db_config():
    missing = [name for name in _REQUIRED_ENV_VARS if not os.environ.get(name)]

    if missing:
        raise RuntimeError(
            "Variáveis de ambiente do PostgreSQL ausentes: "
            + ", ".join(missing)
            + ". Configure DB_HOST, DB_PORT, DB_NAME, DB_USER e DB_PASSWORD no Render."
        )

    return {
        "host": os.environ["DB_HOST"],
        "port": os.environ.get("DB_PORT", "5432"),
        "dbname": os.environ["DB_NAME"],
        "user": os.environ["DB_USER"],
        "password": os.environ["DB_PASSWORD"],
        "sslmode": os.environ.get("DB_SSLMODE", "require"),
    }


def conectar():
    return psycopg2.connect(**_get_db_config())


@contextmanager
def _cursor(commit=False):
    conn = conectar()
    try:
        cursor = conn.cursor()
        try:
            yield cursor
            if commit:
                conn.commit()
        finally:
            cursor.close()
    except Exception:
        if commit:
            conn.rollback()
        raise
    finally:
        conn.close()


def inicializar_banco():
    with _cursor(commit=True) as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS materiais (
                id SERIAL PRIMARY KEY,
                codigo_material TEXT UNIQUE NOT NULL,
                descricao TEXT,
                material TEXT,
                norma TEXT,
                ncm TEXT,
                unidade_medida TEXT,
                codigo_interno_jundiai TEXT,
                codigo_interno_varzea TEXT,
                preco_revisado DOUBLE PRECISION,
                data_ultima_revisao TEXT,
                ativo INTEGER DEFAULT 1,
                data_cadastro TEXT,
                data_atualizacao TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS pedidos (
                id SERIAL PRIMARY KEY,
                numero_pedido TEXT,
                data_emissao TEXT,
                comprador TEXT,
                unidade TEXT,
                data_upload TEXT,
                arquivo_pdf TEXT,
                status_etapa1 TEXT,
                status_etapa2 TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS pedido_itens (
                id SERIAL PRIMARY KEY,
                pedido_id INTEGER REFERENCES pedidos(id),
                item_pedido TEXT,
                codigo_material TEXT,
                descricao TEXT,
                quantidade DOUBLE PRECISION,
                unidade_medida TEXT,
                data_entrega TEXT,
                valor_unitario_pdf DOUBLE PRECISION,
                valor_total_pdf DOUBLE PRECISION,
                material TEXT,
                norma TEXT,
                ncm TEXT,
                leadtime INTEGER
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS auditorias (
                id SERIAL PRIMARY KEY,
                pedido_item_id INTEGER REFERENCES pedido_itens(id),
                data_auditoria TEXT,
                etapa1_status TEXT,
                etapa1_detalhes TEXT,
                etapa2_status TEXT,
                etapa2_detalhes TEXT,
                preco_revisado DOUBLE PRECISION,
                preco_pdf DOUBLE PRECISION,
                diferenca DOUBLE PRECISION
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS regras_fiscais (
                id SERIAL PRIMARY KEY,
                palavra_chave TEXT NOT NULL,
                material TEXT NOT NULL,
                ncm TEXT NOT NULL,
                aliquota_icms DOUBLE PRECISION,
                aliquota_ipi DOUBLE PRECISION,
                observacao TEXT,
                ativo INTEGER DEFAULT 1
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS usuarios (
                id SERIAL PRIMARY KEY,
                nome TEXT NOT NULL,
                usuario TEXT NOT NULL UNIQUE,
                senha TEXT NOT NULL,
                perfil TEXT NOT NULL,
                ativo INTEGER DEFAULT 1
            )
            """
        )

    try:
        inserir_usuario("Administrador", "admin", "admin123", "ADMIN")
    except Exception:
        pass


def listar_materiais():
    with _cursor() as cursor:
        cursor.execute(
            """
            SELECT codigo_material, descricao, material, preco_revisado, data_ultima_revisao
            FROM materiais
            ORDER BY codigo_material
            """
        )
        return cursor.fetchall()


def inserir_material(
    codigo_material,
    descricao,
    material,
    norma,
    ncm,
    unidade_medida,
    codigo_interno_jundiai,
    codigo_interno_varzea,
    preco_revisado,
    data_ultima_revisao,
):
    with _cursor(commit=True) as cursor:
        cursor.execute(
            """
            INSERT INTO materiais (
                codigo_material, descricao, material, norma, ncm, unidade_medida,
                codigo_interno_jundiai, codigo_interno_varzea, preco_revisado, data_ultima_revisao
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (codigo_material) DO UPDATE SET
                descricao = EXCLUDED.descricao,
                material = EXCLUDED.material,
                norma = EXCLUDED.norma,
                ncm = EXCLUDED.ncm,
                unidade_medida = EXCLUDED.unidade_medida,
                codigo_interno_jundiai = EXCLUDED.codigo_interno_jundiai,
                codigo_interno_varzea = EXCLUDED.codigo_interno_varzea,
                preco_revisado = EXCLUDED.preco_revisado,
                data_ultima_revisao = EXCLUDED.data_ultima_revisao
            """,
            (
                codigo_material,
                descricao,
                material,
                norma,
                ncm,
                unidade_medida,
                codigo_interno_jundiai,
                codigo_interno_varzea,
                preco_revisado,
                data_ultima_revisao,
            ),
        )


def buscar_material(codigo):
    with _cursor() as cursor:
        cursor.execute("SELECT * FROM materiais WHERE codigo_material = %s", (codigo,))
        return cursor.fetchone()


def atualizar_material(
    codigo_material,
    descricao,
    material,
    norma,
    ncm,
    unidade_medida,
    codigo_interno_jundiai,
    codigo_interno_varzea,
    preco_revisado,
    data_ultima_revisao,
):
    with _cursor(commit=True) as cursor:
        cursor.execute(
            """
            UPDATE materiais
            SET descricao = %s,
                material = %s,
                norma = %s,
                ncm = %s,
                unidade_medida = %s,
                codigo_interno_jundiai = %s,
                codigo_interno_varzea = %s,
                preco_revisado = %s,
                data_ultima_revisao = %s
            WHERE codigo_material = %s
            """,
            (
                descricao,
                material,
                norma,
                ncm,
                unidade_medida,
                codigo_interno_jundiai,
                codigo_interno_varzea,
                preco_revisado,
                data_ultima_revisao,
                codigo_material,
            ),
        )


def excluir_material(codigo_material):
    with _cursor(commit=True) as cursor:
        cursor.execute("DELETE FROM materiais WHERE codigo_material = %s", (codigo_material,))


def listar_materiais_completo():
    with _cursor() as cursor:
        cursor.execute(
            """
            SELECT codigo_material, descricao, material, norma, ncm, unidade_medida,
                   codigo_interno_jundiai, codigo_interno_varzea, preco_revisado, data_ultima_revisao
            FROM materiais
            ORDER BY codigo_material
            """
        )
        return cursor.fetchall()


def criar_tabela_regras_fiscais():
    inicializar_banco()


def listar_regras_fiscais():
    with _cursor() as cursor:
        cursor.execute(
            """
            SELECT id, palavra_chave, material, ncm, aliquota_icms, aliquota_ipi, observacao, ativo
            FROM regras_fiscais
            ORDER BY palavra_chave
            """
        )
        return cursor.fetchall()


def inserir_regra_fiscal(
    palavra_chave,
    material,
    ncm,
    aliquota_icms,
    aliquota_ipi,
    observacao,
    ativo=1,
):
    with _cursor(commit=True) as cursor:
        cursor.execute(
            """
            INSERT INTO regras_fiscais (
                palavra_chave, material, ncm, aliquota_icms, aliquota_ipi, observacao, ativo
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            """,
            (palavra_chave, material, ncm, aliquota_icms, aliquota_ipi, observacao, ativo),
        )


def buscar_regra_fiscal(id_regra):
    with _cursor() as cursor:
        cursor.execute("SELECT * FROM regras_fiscais WHERE id = %s", (id_regra,))
        return cursor.fetchone()


def atualizar_regra_fiscal(
    id_regra,
    palavra_chave,
    material,
    ncm,
    aliquota_icms,
    aliquota_ipi,
    observacao,
    ativo,
):
    with _cursor(commit=True) as cursor:
        cursor.execute(
            """
            UPDATE regras_fiscais
            SET palavra_chave = %s,
                material = %s,
                ncm = %s,
                aliquota_icms = %s,
                aliquota_ipi = %s,
                observacao = %s,
                ativo = %s
            WHERE id = %s
            """,
            (palavra_chave, material, ncm, aliquota_icms, aliquota_ipi, observacao, ativo, id_regra),
        )


def excluir_regra_fiscal(id_regra):
    with _cursor(commit=True) as cursor:
        cursor.execute("DELETE FROM regras_fiscais WHERE id = %s", (id_regra,))


def localizar_regra_fiscal(descricao, material):
    with _cursor() as cursor:
        cursor.execute(
            """
            SELECT palavra_chave, material, ncm, aliquota_icms, aliquota_ipi
            FROM regras_fiscais
            WHERE ativo = 1
            """
        )
        regras = cursor.fetchall()

    descricao = str(descricao).upper()
    material = str(material).upper()

    for regra in regras:
        palavra = str(regra[0]).upper()
        material_regra = str(regra[1]).upper()

        if palavra in descricao and material_regra in material:
            return {"ncm": regra[2], "icms": regra[3], "ipi": regra[4]}

    return None


def inserir_usuario(nome, usuario, senha, perfil):
    with _cursor(commit=True) as cursor:
        cursor.execute(
            """
            INSERT INTO usuarios (nome, usuario, senha, perfil)
            VALUES (%s,%s,%s,%s)
            """,
            (nome, usuario, senha, perfil),
        )


def buscar_usuario_login(usuario, senha):
    with _cursor() as cursor:
        cursor.execute(
            """
            SELECT id, nome, usuario, perfil
            FROM usuarios
            WHERE usuario = %s
            AND senha = %s
            AND ativo = 1
            """,
            (usuario, senha),
        )
        return cursor.fetchone()


def listar_usuarios():
    with _cursor() as cursor:
        cursor.execute(
            """
            SELECT id, nome, usuario, perfil, ativo
            FROM usuarios
            ORDER BY nome
            """
        )
        return cursor.fetchall()


def excluir_usuario(id_usuario):
    with _cursor(commit=True) as cursor:
        cursor.execute("DELETE FROM usuarios WHERE id = %s", (id_usuario,))


if all(os.environ.get(name) for name in _REQUIRED_ENV_VARS):
    inicializar_banco()
