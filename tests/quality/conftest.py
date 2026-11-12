from pathlib import Path

import duckdb
import pytest

DB_PATH = Path(__file__).resolve().parents[2] / "toys.duckdb"


@pytest.fixture(scope="session")
def con():
    if not DB_PATH.exists():
        pytest.fail(
            f"{DB_PATH} não existe: rode ingestao.py, transformacao.py e marts.py antes"
        )
    conexao = duckdb.connect(str(DB_PATH), read_only=True)
    yield conexao
    conexao.close()


def escalar(con, sql):
    return con.execute(sql).fetchall()[0][0]
