"""Cria o banco de testes (devpulse_test) se ainda não existir."""
import os

import psycopg

url = os.environ["TEST_DATABASE_URL"].replace("+psycopg", "")
base, name = url.rsplit("/", 1)
with psycopg.connect(f"{base}/postgres", autocommit=True) as conn:
    if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone():
        conn.execute(f'CREATE DATABASE "{name}"')
        print(f"Banco {name} criado")
