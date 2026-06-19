
import sqlite3

DB = "database.db"


def conectar():

    return sqlite3.connect(DB)


def listar_materiais():

    conn = conectar()

    cursor = conn.cursor()

    cursor.execute("""

        SELECT
            codigo_material,
            descricao,
            material,
            preco_revisado,
            data_ultima_revisao

        FROM materiais

        ORDER BY codigo_material

    """)

    dados = cursor.fetchall()

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
    data_ultima_revisao

):

    conn = conectar()

    cursor = conn.cursor()

    cursor.execute("""

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

        VALUES (

            ?,?,?,?,?,?,?,?,?,?

        )

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
        data_ultima_revisao

    ))

    conn.commit()

    conn.close()


def buscar_material(codigo):

    conn = conectar()

    cursor = conn.cursor()

    cursor.execute("""

        SELECT *

        FROM materiais

        WHERE codigo_material = ?

    """, (codigo,))

    resultado = cursor.fetchone()

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
    data_ultima_revisao

):

    conn = conectar()

    cursor = conn.cursor()

    cursor.execute("""

        UPDATE materiais

        SET

            descricao = ?,
            material = ?,
            norma = ?,
            ncm = ?,
            unidade_medida = ?,
            codigo_interno_jundiai = ?,
            codigo_interno_varzea = ?,
            preco_revisado = ?,
            data_ultima_revisao = ?

        WHERE codigo_material = ?

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
        codigo_material

    ))

    conn.commit()

    conn.close()

def excluir_material(codigo_material):

    conn = conectar()

    cursor = conn.cursor()

    cursor.execute(

        """

        DELETE FROM materiais

        WHERE codigo_material = ?

        """,

        (codigo_material,)

    )

    conn.commit()

    conn.close()

def listar_materiais_completo():

    conn = conectar()

    cursor = conn.cursor()

    cursor.execute("""

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

    """)

    dados = cursor.fetchall()

    conn.close()

    return dados

def criar_tabela_regras_fiscais():

    conn = conectar()

    cursor = conn.cursor()

    cursor.execute("""

        CREATE TABLE IF NOT EXISTS regras_fiscais (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            palavra_chave TEXT NOT NULL,

            material TEXT NOT NULL,

            ncm TEXT NOT NULL,

            aliquota_icms REAL,

            aliquota_ipi REAL,

            observacao TEXT,

            ativo INTEGER DEFAULT 1

        )

    """)

    conn.commit()

    conn.close()


def listar_regras_fiscais():

    conn = conectar()

    cursor = conn.cursor()

    cursor.execute("""

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

    """)

    dados = cursor.fetchall()

    conn.close()

    return dados


def inserir_regra_fiscal(

    palavra_chave,
    material,
    ncm,
    aliquota_icms,
    aliquota_ipi,
    observacao,
    ativo=1

):

    conn = conectar()

    cursor = conn.cursor()

    cursor.execute("""

        INSERT INTO regras_fiscais (

            palavra_chave,
            material,
            ncm,
            aliquota_icms,
            aliquota_ipi,
            observacao,
            ativo

        )

        VALUES (

            ?,?,?,?,?,?,?

        )

    """,

    (

        palavra_chave,
        material,
        ncm,
        aliquota_icms,
        aliquota_ipi,
        observacao,
        ativo

    ))

    conn.commit()

    conn.close()


def buscar_regra_fiscal(id_regra):

    conn = conectar()

    cursor = conn.cursor()

    cursor.execute(

        """

        SELECT *

        FROM regras_fiscais

        WHERE id = ?

        """,

        (id_regra,)

    )

    resultado = cursor.fetchone()

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
    ativo

):

    conn = conectar()

    cursor = conn.cursor()

    cursor.execute("""

        UPDATE regras_fiscais

        SET

            palavra_chave = ?,
            material = ?,
            ncm = ?,
            aliquota_icms = ?,
            aliquota_ipi = ?,
            observacao = ?,
            ativo = ?

        WHERE id = ?

    """,

    (

        palavra_chave,
        material,
        ncm,
        aliquota_icms,
        aliquota_ipi,
        observacao,
        ativo,
        id_regra

    ))

    conn.commit()

    conn.close()

def excluir_regra_fiscal(id_regra):

    conn = conectar()

    cursor = conn.cursor()

    cursor.execute(

        """

        DELETE FROM regras_fiscais

        WHERE id = ?

        """,

        (id_regra,)

    )

    conn.commit()

    conn.close()

# ====================================
# INICIALIZA TABELAS
# ====================================

criar_tabela_regras_fiscais()

def localizar_regra_fiscal(
    descricao,
    material
):

    conn = conectar()

    cursor = conn.cursor()

    cursor.execute("""

        SELECT

            palavra_chave,
            material,
            ncm,
            aliquota_icms,
            aliquota_ipi

        FROM regras_fiscais

        WHERE ativo = 1

    """)

    regras = cursor.fetchall()

    conn.close()

    descricao = str(descricao).upper()

    material = str(material).upper()

    for regra in regras:

        palavra = str(regra[0]).upper()

        material_regra = str(regra[1]).upper()

        if (

                palavra in descricao

                and

                material_regra in material

        ):

            return {

                "ncm": regra[2],

                "icms": regra[3],

                "ipi": regra[4]

            }

    return None


