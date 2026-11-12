"""Gera o schema marts de toys.duckdb a partir dos arquivos sql/marts/*.sql.

Cada arquivo é um SELECT sobre refined.* e vira a tabela marts.<nome>, onde
<nome> é o nome do arquivo sem o prefixo numérico (01_receita_por_mes.sql ->
marts.receita_por_mes). Os arquivos rodam em ordem de nome. O schema marts é
recriado do zero a cada execução, numa única transação.

Premissas (repetidas no topo de cada SQL):
    receita = units × product_price
    margem  = units × (product_price − product_cost)
"""

import re
from pathlib import Path

import duckdb

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "toys.duckdb"
SQL_DIR = BASE_DIR / "sql" / "marts"

# Marts cuja soma de receita deve bater com a receita total de refined.
MARTS_COM_RECEITA_TOTAL = [
    "receita_por_mes",
    "receita_margem_por_categoria",
    "ranking_lojas",
    "pareto_produtos",
    "receita_por_tipo_localizacao",
    "vendas_mes_loja_produto",
]


def nome_tabela(arquivo: Path) -> str:
    return re.sub(r"^\d+_", "", arquivo.stem)


def main() -> None:
    arquivos = sorted(SQL_DIR.glob("*.sql"))
    if not arquivos:
        raise FileNotFoundError(f"Nenhum arquivo .sql em {SQL_DIR}")

    with duckdb.connect(str(DB_PATH)) as con:
        con.execute("BEGIN TRANSACTION")
        try:
            con.execute("DROP SCHEMA IF EXISTS marts CASCADE")
            con.execute("CREATE SCHEMA marts")

            contagens = {}
            for arquivo in arquivos:
                tabela = nome_tabela(arquivo)
                select = arquivo.read_text(encoding="utf-8").strip().rstrip(";")
                con.execute(f"CREATE TABLE marts.{tabela} AS\n{select}")
                contagens[tabela] = con.execute(
                    f"SELECT count(*) FROM marts.{tabela}"
                ).fetchall()[0][0]

            # Cada mart reparte a mesma receita por um eixo diferente: as somas devem bater.
            (receita_total,) = con.execute(
                "SELECT sum(s.units * p.product_price) "
                "FROM refined.sales s JOIN refined.products p USING (product_id)"
            ).fetchall()[0]
            for tabela in MARTS_COM_RECEITA_TOTAL:
                (soma,) = con.execute(
                    f"SELECT sum(receita) FROM marts.{tabela}"
                ).fetchall()[0]
                if soma != receita_total:
                    raise RuntimeError(
                        f"marts.{tabela}: receita {soma} difere do total {receita_total}"
                    )
        except (duckdb.Error, RuntimeError):
            con.execute("ROLLBACK")
            raise
        con.execute("COMMIT")

    for tabela, n in contagens.items():
        print(f"marts.{tabela}: {n:,} linhas")
    print(f"receita total conferida em todos os marts: {receita_total:,.2f}")


if __name__ == "__main__":
    main()
