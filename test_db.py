from sqlalchemy import text
from src.database.connection import engine

try:
    with engine.connect() as connection:
        result = connection.execute(text("SELECT DATABASE()"))
        print("Conexão estabelecida!")
        print("Banco conectado:", result.scalar())

except Exception as error:
    print("Erro na conexão:", error)