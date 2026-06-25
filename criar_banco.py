"""Cria/atualiza a estrutura de tabelas no PostgreSQL/Supabase."""

from database import inicializar_banco


if __name__ == "__main__":
    inicializar_banco()
    print("Banco PostgreSQL criado/atualizado com sucesso!")
