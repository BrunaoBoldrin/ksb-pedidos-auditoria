import sqlite3

conn = sqlite3.connect("database.db")

cursor = conn.cursor()

cursor.executescript("""

CREATE TABLE IF NOT EXISTS materiais (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    codigo_material TEXT UNIQUE NOT NULL,

    descricao TEXT,

    material TEXT,

    norma TEXT,

    ncm TEXT,

    unidade_medida TEXT,

    codigo_interno_jundiai TEXT,

    codigo_interno_varzea TEXT,

    preco_revisado REAL,

    data_ultima_revisao TEXT,

    ativo INTEGER DEFAULT 1,

    data_cadastro TEXT,

    data_atualizacao TEXT
);

CREATE TABLE IF NOT EXISTS pedidos (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    numero_pedido TEXT,

    data_emissao TEXT,

    comprador TEXT,

    unidade TEXT,

    data_upload TEXT,

    arquivo_pdf TEXT,

    status_etapa1 TEXT,

    status_etapa2 TEXT
);

CREATE TABLE IF NOT EXISTS pedido_itens (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    pedido_id INTEGER,

    item_pedido TEXT,

    codigo_material TEXT,

    descricao TEXT,

    quantidade REAL,

    unidade_medida TEXT,

    data_entrega TEXT,

    valor_unitario_pdf REAL,

    valor_total_pdf REAL,

    material TEXT,

    norma TEXT,

    ncm TEXT,

    leadtime INTEGER,

    FOREIGN KEY (pedido_id)
    REFERENCES pedidos(id)
);

CREATE TABLE IF NOT EXISTS auditorias (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    pedido_item_id INTEGER,

    data_auditoria TEXT,

    etapa1_status TEXT,

    etapa1_detalhes TEXT,

    etapa2_status TEXT,

    etapa2_detalhes TEXT,

    preco_revisado REAL,

    preco_pdf REAL,

    diferenca REAL,

    FOREIGN KEY (pedido_item_id)
    REFERENCES pedido_itens(id)
);

""")

conn.commit()

conn.close()

print("Banco criado com sucesso!")

