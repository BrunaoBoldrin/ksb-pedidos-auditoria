"""Camada de acesso a dados PostgreSQL/Neon.

Mantém as funções públicas usadas pelo app.py e parser.py.
"""

import os
from contextlib import contextmanager

import psycopg2


_REQUIRED_ENV_VARS = ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD")


def _limpar_codigo(codigo):
    return str(codigo or "").strip()


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
                codigo_material TEXT,
                descricao TEXT,
                material TEXT,
                norma TEXT,
                ncm TEXT,
                unidade_medida TEXT,
                codigo_interno_jundiai TEXT,
                codigo_interno_varzea TEXT,
                preco_revisado DOUBLE PRECISION,
                data_ultima_revisao TEXT,
                usuario_ultima_revisao_preco TEXT,
                ativo INTEGER DEFAULT 1,
                data_cadastro TEXT,
                data_atualizacao TEXT
            )
            """
        )
        cursor.execute("ALTER TABLE materiais ADD COLUMN IF NOT EXISTS usuario_ultima_revisao_preco TEXT")
        cursor.execute("UPDATE materiais SET codigo_material = BTRIM(codigo_material) WHERE codigo_material IS NOT NULL")
        cursor.execute("DELETE FROM materiais WHERE codigo_material IS NULL OR BTRIM(codigo_material) = ''")

        # Consolida duplicados antes de criar índice único.
        # Mantém o menor ID e preenche cada campo com o primeiro valor não vazio encontrado no grupo.
        cursor.execute(
            """
            WITH grupos AS (
                SELECT
                    BTRIM(codigo_material) AS codigo,
                    MIN(id) AS id_keep,
                    (ARRAY_AGG(NULLIF(descricao, '') ORDER BY id DESC) FILTER (WHERE NULLIF(descricao, '') IS NOT NULL))[1] AS descricao_v,
                    (ARRAY_AGG(NULLIF(material, '') ORDER BY id DESC) FILTER (WHERE NULLIF(material, '') IS NOT NULL))[1] AS material_v,
                    (ARRAY_AGG(NULLIF(norma, '') ORDER BY id DESC) FILTER (WHERE NULLIF(norma, '') IS NOT NULL))[1] AS norma_v,
                    (ARRAY_AGG(NULLIF(ncm, '') ORDER BY id DESC) FILTER (WHERE NULLIF(ncm, '') IS NOT NULL))[1] AS ncm_v,
                    (ARRAY_AGG(NULLIF(unidade_medida, '') ORDER BY id DESC) FILTER (WHERE NULLIF(unidade_medida, '') IS NOT NULL))[1] AS unidade_v,
                    (ARRAY_AGG(NULLIF(codigo_interno_jundiai, '') ORDER BY id DESC) FILTER (WHERE NULLIF(codigo_interno_jundiai, '') IS NOT NULL))[1] AS jundiai_v,
                    (ARRAY_AGG(NULLIF(codigo_interno_varzea, '') ORDER BY id DESC) FILTER (WHERE NULLIF(codigo_interno_varzea, '') IS NOT NULL))[1] AS varzea_v,
                    (ARRAY_AGG(preco_revisado ORDER BY id DESC) FILTER (WHERE preco_revisado IS NOT NULL))[1] AS preco_v,
                    (ARRAY_AGG(NULLIF(data_ultima_revisao, '') ORDER BY id DESC) FILTER (WHERE NULLIF(data_ultima_revisao, '') IS NOT NULL))[1] AS data_v,
                    (ARRAY_AGG(NULLIF(usuario_ultima_revisao_preco, '') ORDER BY id DESC) FILTER (WHERE NULLIF(usuario_ultima_revisao_preco, '') IS NOT NULL))[1] AS usuario_v
                FROM materiais
                GROUP BY BTRIM(codigo_material)
                HAVING COUNT(*) > 1
            )
            UPDATE materiais m
            SET descricao = COALESCE(g.descricao_v, m.descricao),
                material = COALESCE(g.material_v, m.material),
                norma = COALESCE(g.norma_v, m.norma),
                ncm = COALESCE(g.ncm_v, m.ncm),
                unidade_medida = COALESCE(g.unidade_v, m.unidade_medida),
                codigo_interno_jundiai = COALESCE(g.jundiai_v, m.codigo_interno_jundiai),
                codigo_interno_varzea = COALESCE(g.varzea_v, m.codigo_interno_varzea),
                preco_revisado = COALESCE(g.preco_v, m.preco_revisado),
                data_ultima_revisao = COALESCE(g.data_v, m.data_ultima_revisao),
                usuario_ultima_revisao_preco = COALESCE(g.usuario_v, m.usuario_ultima_revisao_preco)
            FROM grupos g
            WHERE m.id = g.id_keep
            """
        )
        cursor.execute(
            """
            DELETE FROM materiais m
            USING materiais keep
            WHERE BTRIM(m.codigo_material) = BTRIM(keep.codigo_material)
              AND m.id > keep.id
            """
        )
        cursor.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_materiais_codigo_material_unico
            ON materiais (codigo_material)
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
                palavra_chave TEXT,
                material TEXT,
                ncm TEXT NOT NULL,
                aliquota_icms DOUBLE PRECISION,
                aliquota_ipi DOUBLE PRECISION,
                observacao TEXT,
                ativo INTEGER DEFAULT 1
            )
            """
        )
        cursor.execute("ALTER TABLE regras_fiscais ALTER COLUMN palavra_chave DROP NOT NULL")
        cursor.execute("ALTER TABLE regras_fiscais ALTER COLUMN material DROP NOT NULL")
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


def _material_existe(codigo_material):
    codigo_material = _limpar_codigo(codigo_material)
    with _cursor() as cursor:
        cursor.execute(
            "SELECT id FROM materiais WHERE codigo_material = %s LIMIT 1",
            (codigo_material,),
        )
        linha = cursor.fetchone()
    return linha[0] if linha else None


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
    usuario_ultima_revisao_preco=None,
):
    codigo_material = _limpar_codigo(codigo_material)
    id_existente = _material_existe(codigo_material)

    if id_existente:
        atualizar_material(
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
            usuario_ultima_revisao_preco,
        )
        return

    with _cursor(commit=True) as cursor:
        cursor.execute(
            """
            INSERT INTO materiais (
                codigo_material, descricao, material, norma, ncm, unidade_medida,
                codigo_interno_jundiai, codigo_interno_varzea, preco_revisado,
                data_ultima_revisao, usuario_ultima_revisao_preco
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
                usuario_ultima_revisao_preco,
            ),
        )


def buscar_material(codigo):
    codigo = _limpar_codigo(codigo)
    with _cursor() as cursor:
        cursor.execute("SELECT * FROM materiais WHERE codigo_material = %s LIMIT 1", (codigo,))
        return cursor.fetchone()


def buscar_material_por_codigo(codigo_material):
    codigo_material = _limpar_codigo(codigo_material)
    with _cursor() as cursor:
        cursor.execute(
            """
            SELECT codigo_material, descricao, material, norma, ncm, unidade_medida,
                   codigo_interno_jundiai, codigo_interno_varzea, preco_revisado,
                   data_ultima_revisao, usuario_ultima_revisao_preco
            FROM materiais
            WHERE codigo_material = %s
            LIMIT 1
            """,
            (codigo_material,),
        )
        linha = cursor.fetchone()

    if not linha:
        return None

    return {
        "codigo_material": linha[0],
        "descricao": linha[1],
        "material": linha[2],
        "norma": linha[3],
        "ncm": linha[4],
        "unidade_medida": linha[5],
        "codigo_interno_jundiai": linha[6],
        "codigo_interno_varzea": linha[7],
        "preco_unitario_liquido": linha[8],
        "data_ultima_revisao": linha[9],
        "usuario_ultima_revisao_preco": linha[10],
    }


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
    usuario_ultima_revisao_preco=None,
):
    codigo_material = _limpar_codigo(codigo_material)
    with _cursor(commit=True) as cursor:
        cursor.execute(
            """
            UPDATE materiais
            SET descricao = COALESCE(NULLIF(%s, ''), descricao),
                material = COALESCE(NULLIF(%s, ''), material),
                norma = COALESCE(NULLIF(%s, ''), norma),
                ncm = COALESCE(NULLIF(%s, ''), ncm),
                unidade_medida = COALESCE(NULLIF(%s, ''), unidade_medida),
                codigo_interno_jundiai = COALESCE(NULLIF(%s, ''), codigo_interno_jundiai),
                codigo_interno_varzea = COALESCE(NULLIF(%s, ''), codigo_interno_varzea),
                preco_revisado = COALESCE(%s, preco_revisado),
                data_ultima_revisao = COALESCE(NULLIF(%s, ''), data_ultima_revisao),
                usuario_ultima_revisao_preco = COALESCE(NULLIF(%s, ''), usuario_ultima_revisao_preco)
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
                usuario_ultima_revisao_preco,
                codigo_material,
            ),
        )


def excluir_material(codigo_material):
    codigo_material = _limpar_codigo(codigo_material)
    with _cursor(commit=True) as cursor:
        cursor.execute("DELETE FROM materiais WHERE codigo_material = %s", (codigo_material,))


def listar_materiais_completo():
    with _cursor() as cursor:
        cursor.execute(
            """
            SELECT codigo_material, descricao, material, norma, ncm, unidade_medida,
                   codigo_interno_jundiai, codigo_interno_varzea, preco_revisado,
                   data_ultima_revisao, usuario_ultima_revisao_preco
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
            SELECT id, ncm, aliquota_icms, aliquota_ipi, observacao, ativo
            FROM regras_fiscais
            ORDER BY ncm
            """
        )
        return cursor.fetchall()


def inserir_regra_fiscal(ncm, aliquota_icms, aliquota_ipi, observacao, ativo=1):
    with _cursor(commit=True) as cursor:
        cursor.execute(
            """
            INSERT INTO regras_fiscais (ncm, aliquota_icms, aliquota_ipi, observacao, ativo)
            VALUES (%s,%s,%s,%s,%s)
            """,
            (ncm, aliquota_icms, aliquota_ipi, observacao, ativo),
        )


def buscar_regra_fiscal(id_regra):
    with _cursor() as cursor:
        cursor.execute(
            """
            SELECT id, ncm, aliquota_icms, aliquota_ipi, observacao, ativo
            FROM regras_fiscais
            WHERE id = %s
            """,
            (id_regra,),
        )
        return cursor.fetchone()


def atualizar_regra_fiscal(id_regra, ncm, aliquota_icms, aliquota_ipi, observacao, ativo):
    with _cursor(commit=True) as cursor:
        cursor.execute(
            """
            UPDATE regras_fiscais
            SET ncm = %s,
                aliquota_icms = %s,
                aliquota_ipi = %s,
                observacao = %s,
                ativo = %s
            WHERE id = %s
            """,
            (ncm, aliquota_icms, aliquota_ipi, observacao, ativo, id_regra),
        )


def excluir_regra_fiscal(id_regra):
    with _cursor(commit=True) as cursor:
        cursor.execute("DELETE FROM regras_fiscais WHERE id = %s", (id_regra,))


def localizar_regra_fiscal(descricao, material):
    return None


def localizar_regra_fiscal_por_ncm(ncm):
    with _cursor() as cursor:
        cursor.execute(
            """
            SELECT ncm, aliquota_icms, aliquota_ipi, observacao
            FROM regras_fiscais
            WHERE ativo = 1
            AND REPLACE(REPLACE(ncm, '.', ''), ' ', '') = REPLACE(REPLACE(%s, '.', ''), ' ', '')
            ORDER BY id DESC
            LIMIT 1
            """,
            (str(ncm),),
        )
        linha = cursor.fetchone()

    if not linha:
        return None

    return {"ncm": linha[0], "icms": linha[1], "ipi": linha[2], "observacao": linha[3]}


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
