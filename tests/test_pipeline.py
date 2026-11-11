"""Testes de integridade do toys.duckdb: contagens, chaves únicas e receita.

As contagens esperadas vêm da carga atual (Maven Toys, jan/2017 a set/2018).
Se os arquivos de raw/ mudarem, estes números precisam ser revistos.
"""

from decimal import Decimal

import pytest
from conftest import escalar

RECEITA_TOTAL = Decimal("14444572.35")

CONTAGENS = {
    "raw.sales": 829_262,
    "raw.products": 35,
    "raw.stores": 50,
    "raw.inventory": 1_593,
    "refined.sales": 829_262,
    "refined.products": 35,
    "refined.stores": 50,
    "refined.inventory": 1_593,
    "marts.receita_por_mes": 21,
    "marts.receita_margem_por_categoria": 5,
    "marts.ranking_lojas": 50,
    "marts.pareto_produtos": 35,
    "marts.receita_por_tipo_localizacao": 4,
    "marts.vendas_mes_loja_produto": 22_931,
}

CHAVES = {
    "raw.sales": "Sale_ID",
    "raw.products": "Product_ID",
    "raw.stores": "Store_ID",
    "raw.inventory": "Store_ID, Product_ID",
    "refined.sales": "sale_id",
    "refined.products": "product_id",
    "refined.stores": "store_id",
    "refined.inventory": "store_id, product_id",
    "marts.receita_por_mes": "mes",
    "marts.receita_margem_por_categoria": "categoria",
    "marts.ranking_lojas": "store_id",
    "marts.pareto_produtos": "product_id",
    "marts.receita_por_tipo_localizacao": "tipo_localizacao",
    "marts.vendas_mes_loja_produto": "mes, store_id, product_id",
}

MARTS_COM_RECEITA = [t for t in CONTAGENS if t.startswith("marts.")]


@pytest.mark.parametrize("tabela, esperado", CONTAGENS.items())
def test_contagem(con, tabela, esperado):
    assert escalar(con, f"SELECT count(*) FROM {tabela}") == esperado


@pytest.mark.parametrize("tabela, chave", CHAVES.items())
def test_chave_unica(con, tabela, chave):
    duplicadas = escalar(
        con,
        f"SELECT count(*) FROM (SELECT {chave} FROM {tabela} "
        f"GROUP BY {chave} HAVING count(*) > 1)",
    )
    nulas = escalar(
        con,
        f"SELECT count(*) FROM {tabela} WHERE "
        + " OR ".join(f"{c.strip()} IS NULL" for c in chave.split(",")),
    )
    assert (duplicadas, nulas) == (0, 0)


def test_receita_total_refined(con):
    receita = escalar(
        con,
        "SELECT sum(s.units * p.product_price) "
        "FROM refined.sales s JOIN refined.products p USING (product_id)",
    )
    assert receita == RECEITA_TOTAL


@pytest.mark.parametrize("tabela", MARTS_COM_RECEITA)
def test_receita_total_bate_com_refined(con, tabela):
    assert escalar(con, f"SELECT sum(receita) FROM {tabela}") == RECEITA_TOTAL


def test_mart_do_painel_bate_unidades_e_margem_com_refined(con):
    """O painel agrega tudo a partir de marts.vendas_mes_loja_produto."""
    refined = con.execute(
        "SELECT sum(s.units), sum(s.units * (p.product_price - p.product_cost)) "
        "FROM refined.sales s JOIN refined.products p USING (product_id)"
    ).fetchall()[0]
    mart = con.execute(
        "SELECT sum(unidades), sum(margem) FROM marts.vendas_mes_loja_produto"
    ).fetchall()[0]
    assert mart == refined
