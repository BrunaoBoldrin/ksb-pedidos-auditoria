"""Camada de acesso a dados PostgreSQL/Neon."""

import os
from contextlib import contextmanager

import psycopg2

_REQUIRED_ENV_VARS = ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD")


def _limpar_texto(valor):
    if valor is None:
        return ""
    texto = str(valor).strip()
    if texto.lower() in ("nan", "none", "nat"):
        return ""
    return texto


def _limpar_codigo(codigo):
    return _limpar_texto(codigo)


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
                codigo_material TEXT PRIMARY KEY,
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
        cursor.execute("DELETE FROM materiais WHERE codigo_material IS NULL OR BTRIM(codigo_material) = ''")

        # IMPORTANTE:
        # Não pode fazer UPDATE codigo_material = BTRIM(codigo_material) antes de consolidar.
        # Se existirem '01752467' e '01752467 ', o PostgreSQL dispara UniqueViolation.
        # Por isso consolidamos usando BTRIM() + ctid, apagamos duplicados e só depois normalizamos o código.
        cursor.execute(
            """
            WITH ranked AS (
                SELECT
                    ctid,
                    BTRIM(codigo_material) AS codigo,
                    ROW_NUMBER() OVER (PARTITION BY BTRIM(codigo_material) ORDER BY ctid) AS rn
                FROM materiais
                WHERE codigo_material IS NOT NULL
            ), grupos AS (
                SELECT
                    r.codigo,
                    (ARRAY_AGG(r.ctid ORDER BY r.rn))[1] AS keep_ctid,
                    (ARRAY_AGG(NULLIF(m.descricao, '') ORDER BY r.rn DESC) FILTER (WHERE NULLIF(m.descricao, '') IS NOT NULL))[1] AS descricao_v,
                    (ARRAY_AGG(NULLIF(m.material, '') ORDER BY r.rn DESC) FILTER (WHERE NULLIF(m.material, '') IS NOT NULL))[1] AS material_v,
                    (ARRAY_AGG(NULLIF(m.norma, '') ORDER BY r.rn DESC) FILTER (WHERE NULLIF(m.norma, '') IS NOT NULL))[1] AS norma_v,
                    (ARRAY_AGG(NULLIF(m.ncm, '') ORDER BY r.rn DESC) FILTER (WHERE NULLIF(m.ncm, '') IS NOT NULL))[1] AS ncm_v,
                    (ARRAY_AGG(NULLIF(m.unidade_medida, '') ORDER BY r.rn DESC) FILTER (WHERE NULLIF(m.unidade_medida, '') IS NOT NULL))[1] AS unidade_v,
                    (ARRAY_AGG(NULLIF(m.codigo_interno_jundiai, '') ORDER BY r.rn DESC) FILTER (WHERE NULLIF(m.codigo_interno_jundiai, '') IS NOT NULL))[1] AS jundiai_v,
                    (ARRAY_AGG(NULLIF(m.codigo_interno_varzea, '') ORDER BY r.rn DESC) FILTER (WHERE NULLIF(m.codigo_interno_varzea, '') IS NOT NULL))[1] AS varzea_v,
                    (ARRAY_AGG(m.preco_revisado ORDER BY r.rn DESC) FILTER (WHERE m.preco_revisado IS NOT NULL))[1] AS preco_v,
                    (ARRAY_AGG(NULLIF(m.data_ultima_revisao, '') ORDER BY r.rn DESC) FILTER (WHERE NULLIF(m.data_ultima_revisao, '') IS NOT NULL))[1] AS data_v,
                    (ARRAY_AGG(NULLIF(m.usuario_ultima_revisao_preco, '') ORDER BY r.rn DESC) FILTER (WHERE NULLIF(m.usuario_ultima_revisao_preco, '') IS NOT NULL))[1] AS usuario_v
                FROM ranked r
                JOIN materiais m ON m.ctid = r.ctid
                GROUP BY r.codigo
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
            WHERE m.ctid = g.keep_ctid
            """
        )
        cursor.execute(
            """
            WITH ranked AS (
                SELECT
                    ctid,
                    BTRIM(codigo_material) AS codigo,
                    ROW_NUMBER() OVER (PARTITION BY BTRIM(codigo_material) ORDER BY ctid) AS rn
                FROM materiais
                WHERE codigo_material IS NOT NULL
            )
            DELETE FROM materiais m
            USING ranked r
            WHERE m.ctid = r.ctid
              AND r.rn > 1
            """
        )
        cursor.execute("UPDATE materiais SET codigo_material = BTRIM(codigo_material) WHERE codigo_material IS NOT NULL")
        cursor.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_materiais_codigo_material_trim_unico
            ON materiais (BTRIM(codigo_material))
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


def buscar_material(codigo):
    codigo = _limpar_codigo(codigo)
    with _cursor() as cursor:
        cursor.execute("SELECT * FROM materiais WHERE BTRIM(codigo_material) = %s LIMIT 1", (codigo,))
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
            WHERE BTRIM(codigo_material) = %s
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
    descricao = _limpar_texto(descricao)
    material = _limpar_texto(material)
    norma = _limpar_texto(norma)
    ncm = _limpar_texto(ncm)
    unidade_medida = _limpar_texto(unidade_medida)
    codigo_interno_jundiai = _limpar_texto(codigo_interno_jundiai)
    codigo_interno_varzea = _limpar_texto(codigo_interno_varzea)
    data_ultima_revisao = _limpar_texto(data_ultima_revisao)
    usuario_ultima_revisao_preco = _limpar_texto(usuario_ultima_revisao_preco)

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
            WHERE BTRIM(codigo_material) = %s
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
        if cursor.rowcount == 0:
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


def excluir_material(codigo_material):
    codigo_material = _limpar_codigo(codigo_material)
    with _cursor(commit=True) as cursor:
        cursor.execute("DELETE FROM materiais WHERE BTRIM(codigo_material) = %s", (codigo_material,))


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
