import os
import psycopg2


# ====================================
# CONEXAO POSTGRESQL / SUPABASE
# ====================================


def conectar():
    """Abre conexão com PostgreSQL/Supabase usando variáveis de ambiente."""

    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ.get("DB_PORT", "5432"),
        database=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        sslmode=os.environ.get("DB_SSLMODE", "require"),
    )


# ====================================
# CRIACAO DE TABELAS
# ====================================


def criar_tabela_materiais():
    conn = conectar()
    cursor = conn.cursor()

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
            preco_revisado NUMERIC,
            data_ultima_revisao TEXT
        )
        """
    )

    conn.commit()
    cursor.close()
    conn.close()


def criar_tabela_regras_fiscais():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS regras_fiscais (
            id BIGSERIAL PRIMARY KEY,
            palavra_chave TEXT NOT NULL,
            material TEXT NOT NULL,
            ncm TEXT NOT NULL,
            aliquota_icms NUMERIC,
            aliquota_ipi NUMERIC,
            observacao TEXT,
            ativo INTEGER DEFAULT 1
        )
        """
    )

    conn.commit()
    cursor.close()
    conn.close()


def criar_tabela_usuarios():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id BIGSERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            usuario TEXT NOT NULL UNIQUE,
            senha TEXT NOT NULL,
            perfil TEXT NOT NULL,
            ativo INTEGER DEFAULT 1
        )
        """
    )

    conn.commit()
    cursor.close()
    conn.close()


# ====================================
# MATERIAIS
# ====================================


def listar_materiais():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            codigo_material,
            descricao,
            material,
            preco_revisado,
            data_ultima_revisao
        FROM materiais
        ORDER BY codigo_material
        """
    )

    dados = cursor.fetchall()

    cursor.close()
    conn.close()

    return dados


def listar_materiais_completo():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            codigo_material,
            descricao,
            material,
            norma,
            ncm,
            unidade_medida,
            codigo_interno_jundiai,
            codigo_interno_varzea,
            preco_revisado,
            data_ultima_revisao
        FROM materiais
        ORDER BY codigo_material
        """
    )

    dados = cursor.fetchall()

    cursor.close()
    conn.close()

    return dados


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
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO materiais (
            codigo_material,
            descricao,
            material,
            norma,
            ncm,
            unidade_medida,
            codigo_interno_jundiai,
            codigo_interno_varzea,
            preco_revisado,
            data_ultima_revisao
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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

    conn.commit()
    cursor.close()
    conn.close()


def buscar_material(codigo):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM materiais
        WHERE codigo_material = %s
        """,
        (codigo,),
    )

    resultado = cursor.fetchone()

    cursor.close()
    conn.close()

    return resultado


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
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE materiais
        SET
            descricao = %s,
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

    conn.commit()
    cursor.close()
    conn.close()


def excluir_material(codigo_material):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM materiais
        WHERE codigo_material = %s
        """,
        (codigo_material,),
    )

    conn.commit()
    cursor.close()
    conn.close()


# ====================================
# REGRAS FISCAIS
# ====================================


def listar_regras_fiscais():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            id,
            palavra_chave,
            material,
            ncm,
            aliquota_icms,
            aliquota_ipi,
            observacao,
            ativo
        FROM regras_fiscais
        ORDER BY palavra_chave
        """
    )

    dados = cursor.fetchall()

    cursor.close()
    conn.close()

    return dados


def inserir_regra_fiscal(
    palavra_chave,
    material,
    ncm,
    aliquota_icms,
    aliquota_ipi,
    observacao,
    ativo=1,
):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO regras_fiscais (
            palavra_chave,
            material,
            ncm,
            aliquota_icms,
            aliquota_ipi,
            observacao,
            ativo
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            palavra_chave,
            material,
            ncm,
            aliquota_icms,
            aliquota_ipi,
            observacao,
            ativo,
        ),
    )

    conn.commit()
    cursor.close()
    conn.close()


def buscar_regra_fiscal(id_regra):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM regras_fiscais
        WHERE id = %s
        """,
        (id_regra,),
    )

    resultado = cursor.fetchone()

    cursor.close()
    conn.close()

    return resultado


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
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE regras_fiscais
        SET
            palavra_chave = %s,
            material = %s,
            ncm = %s,
            aliquota_icms = %s,
            aliquota_ipi = %s,
            observacao = %s,
            ativo = %s
        WHERE id = %s
        """,
        (
            palavra_chave,
            material,
            ncm,
            aliquota_icms,
            aliquota_ipi,
            observacao,
            ativo,
            id_regra,
        ),
    )

    conn.commit()
    cursor.close()
    conn.close()


def excluir_regra_fiscal(id_regra):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM regras_fiscais
        WHERE id = %s
        """,
        (id_regra,),
    )

    conn.commit()
    cursor.close()
    conn.close()


def localizar_regra_fiscal(descricao, material):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            palavra_chave,
            material,
            ncm,
            aliquota_icms,
            aliquota_ipi
        FROM regras_fiscais
        WHERE ativo = 1
        """
    )

    regras = cursor.fetchall()

    cursor.close()
    conn.close()

    descricao = str(descricao).upper()
    material = str(material).upper()

    for regra in regras:
        palavra = str(regra[0]).upper()
        material_regra = str(regra[1]).upper()

        if palavra in descricao and material_regra in material:
            return {
                "ncm": regra[2],
                "icms": regra[3],
                "ipi": regra[4],
            }

    return None


# ====================================
# USUARIOS - COMPATIBILIDADE FUTURA
# ====================================


def inserir_usuario(nome, usuario, senha, perfil):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO usuarios (
            nome,
            usuario,
            senha,
            perfil
        )
        VALUES (%s,%s,%s,%s)
        """,
        (nome, usuario, senha, perfil),
    )

    conn.commit()
    cursor.close()
    conn.close()


def buscar_usuario_login(usuario, senha):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            id,
            nome,
            usuario,
            perfil
        FROM usuarios
        WHERE usuario = %s
        AND senha = %s
        AND ativo = 1
        """,
        (usuario, senha),
    )

    resultado = cursor.fetchone()

    cursor.close()
    conn.close()

    return resultado


def listar_usuarios():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            id,
            nome,
            usuario,
            perfil,
            ativo
        FROM usuarios
        ORDER BY nome
        """
    )

    dados = cursor.fetchall()

    cursor.close()
    conn.close()

    return dados


def excluir_usuario(id_usuario):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM usuarios
        WHERE id = %s
        """,
        (id_usuario,),
    )

    conn.commit()
    cursor.close()
    conn.close()


# ====================================
# INICIALIZA TABELAS
# ====================================


def inicializar_banco():
    criar_tabela_materiais()
    criar_tabela_regras_fiscais()
    criar_tabela_usuarios()

    try:
        inserir_usuario(
            "Administrador",
            "admin",
            "admin123",
            "ADMIN",
        )
    except Exception:
        pass


inicializar_banco()
