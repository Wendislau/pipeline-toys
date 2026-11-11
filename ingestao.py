"""Ingestão dos CSVs brutos (raw/*.csv.gz) para o schema `raw` de toys.duckdb.

Cada arquivo vira uma tabela raw.<nome>, com todas as colunas como VARCHAR.
O schema raw é recriado do zero a cada execução. Os arquivos em raw/ são
apenas lidos, nunca alterados.
"""

from pathlib import Path

import duckdb

BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "raw"
DB_PATH = BASE_DIR / "toys.duckdb"
TABELAS = ["inventory", "products", "sales", "stores"]


def main() -> None:
    arquivos = {t: RAW_DIR / f"{t}.csv.gz" for t in TABELAS}
    faltando = [str(p) for p in arquivos.values() if not p.exists()]
    if faltando:
        raise FileNotFoundError(f"Arquivos não encontrados: {', '.join(faltando)}")

    with duckdb.connect(str(DB_PATH)) as con:
        con.execute("BEGIN TRANSACTION")
        con.execute("DROP SCHEMA IF EXISTS raw CASCADE")
        con.execute("CREATE SCHEMA raw")
        for tabela, caminho in arquivos.items():
            con.execute(
                f"CREATE TABLE raw.{tabela} AS "
                "SELECT * FROM read_csv(?, header = true, all_varchar = true)",
                [str(caminho)],
            )
        con.execute("COMMIT")

        for tabela in TABELAS:
            (n,) = con.execute(f"SELECT count(*) FROM raw.{tabela}").fetchone()
            print(f"raw.{tabela}: {n:,} linhas")


if __name__ == "__main__":
    main()
