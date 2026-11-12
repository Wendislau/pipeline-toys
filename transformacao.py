"""Transformação raw -> refined em toys.duckdb, conforme specs/refined.md.

Tipagem estrita (CAST, não TRY_CAST): um valor inválido numa carga futura faz a
execução falhar em vez de virar NULL. Chaves primárias e estrangeiras são
declaradas para que duplicatas e órfãos também quebrem a carga. O schema refined
é recriado do zero a cada execução, numa única transação.
"""

from pathlib import Path

import duckdb

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "toys.duckdb"

# Ordem importa: dimensões antes das tabelas que as referenciam.
TABELAS = ["products", "stores", "sales", "inventory"]

DDL = """
CREATE SCHEMA refined;

CREATE TABLE refined.products (
    product_id       INTEGER       PRIMARY KEY,
    product_name     VARCHAR       NOT NULL,
    product_category VARCHAR       NOT NULL,
    product_cost     DECIMAL(10,2) NOT NULL,
    product_price    DECIMAL(10,2) NOT NULL
);

CREATE TABLE refined.stores (
    store_id        INTEGER PRIMARY KEY,
    store_name      VARCHAR NOT NULL,
    store_city      VARCHAR NOT NULL,
    store_location  VARCHAR NOT NULL,
    store_open_date DATE    NOT NULL
);

CREATE TABLE refined.sales (
    sale_id    INTEGER PRIMARY KEY,
    sale_date  DATE    NOT NULL,
    store_id   INTEGER NOT NULL REFERENCES refined.stores (store_id),
    product_id INTEGER NOT NULL REFERENCES refined.products (product_id),
    units      INTEGER NOT NULL CHECK (units > 0)
);

CREATE TABLE refined.inventory (
    store_id      INTEGER NOT NULL REFERENCES refined.stores (store_id),
    product_id    INTEGER NOT NULL REFERENCES refined.products (product_id),
    stock_on_hand INTEGER NOT NULL CHECK (stock_on_hand >= 0),
    PRIMARY KEY (store_id, product_id)
);
"""

CARGAS = {
    # Custo/preço vêm como "$9.99 ": remove "$" e espaços antes de converter.
    "products": """
        INSERT INTO refined.products
        SELECT
            CAST(Product_ID AS INTEGER),
            Product_Name,
            Product_Category,
            CAST(trim(replace(Product_Cost, '$', '')) AS DECIMAL(10,2)),
            CAST(trim(replace(Product_Price, '$', '')) AS DECIMAL(10,2))
        FROM raw.products
    """,
    # Única correção de valor: erro de digitação "Cuidad de Mexico" (4 lojas).
    "stores": """
        INSERT INTO refined.stores
        SELECT
            CAST(Store_ID AS INTEGER),
            Store_Name,
            CASE WHEN Store_City = 'Cuidad de Mexico' THEN 'Ciudad de Mexico'
                 ELSE Store_City END,
            Store_Location,
            CAST(Store_Open_Date AS DATE)
        FROM raw.stores
    """,
    "sales": """
        INSERT INTO refined.sales
        SELECT
            CAST(Sale_ID AS INTEGER),
            CAST("Date" AS DATE),
            CAST(Store_ID AS INTEGER),
            CAST(Product_ID AS INTEGER),
            CAST(Units AS INTEGER)
        FROM raw.sales
    """,
    "inventory": """
        INSERT INTO refined.inventory
        SELECT
            CAST(Store_ID AS INTEGER),
            CAST(Product_ID AS INTEGER),
            CAST(Stock_On_Hand AS INTEGER)
        FROM raw.inventory
    """,
}


def contar(con: duckdb.DuckDBPyConnection, tabela: str) -> int:
    return con.execute(f"SELECT count(*) FROM {tabela}").fetchall()[0][0]


def main() -> None:
    with duckdb.connect(str(DB_PATH)) as con:
        con.execute("BEGIN TRANSACTION")
        try:
            con.execute("DROP SCHEMA IF EXISTS refined CASCADE")
            con.execute(DDL)
            for tabela in TABELAS:
                con.execute(CARGAS[tabela])

            # A spec não descarta linhas: refined deve ter exatamente o mesmo volume de raw.
            contagens = {}
            for tabela in TABELAS:
                n_raw = contar(con, f"raw.{tabela}")
                n_ref = contar(con, f"refined.{tabela}")
                if n_raw != n_ref:
                    raise RuntimeError(
                        f"refined.{tabela} tem {n_ref} linhas, raw.{tabela} tem {n_raw}"
                    )
                contagens[tabela] = n_ref
        except (duckdb.Error, RuntimeError):
            con.execute("ROLLBACK")
            raise
        con.execute("COMMIT")

    for tabela, n in contagens.items():
        print(f"refined.{tabela}: {n:,} linhas")


if __name__ == "__main__":
    main()
