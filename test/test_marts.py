"""Testes unitários do mart 01 (receita_por_mes) sobre tabelas inventadas."""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from apoio import apontar_pipeline, consultar, escrever_raw

import ingestao
import marts
import transformacao

# Preços e custos escolhidos para a conta ter centavos e margens diferentes.
CUSTO = {1: Decimal("6.00"), 2: Decimal("1.75")}
PRECO = {1: Decimal("10.00"), 2: Decimal("2.50")}

PRODUTOS = [
    # Produto caro, margem de 4,00 por unidade.
    ["1", "Robô", "Electronics", "$6.00 ", "$10.00 "],
    # Produto barato com centavos, margem de 0,75 por unidade.
    ["2", "Pião", "Toys", "$1.75 ", "$2.50 "],
]
LOJAS = [
    # Duas lojas, para o mês somar vendas de lojas diferentes.
    ["1", "Loja A", "Guadalajara", "Downtown", "2010-01-01"],
    ["2", "Loja B", "Monterrey", "Airport", "2011-01-01"],
]
VENDAS = [
    # (sale_id, data, loja, produto, unidades)
    # Janeiro: dois produtos em lojas diferentes.
    ["1", "2017-01-01", "1", "1", "3"],
    ["2", "2017-01-20", "2", "2", "4"],
    # Último dia de janeiro: tem de cair em janeiro, não em fevereiro.
    ["3", "2017-01-31", "1", "2", "1"],
    # Fevereiro: uma única venda, para o mês ter valor conhecido isolado.
    ["4", "2017-02-01", "2", "1", "2"],
    # Março não tem venda e não deve aparecer no mart.
]
ESTOQUE = [
    # Um par loja × produto basta: o mart 01 não usa estoque.
    ["1", "1", "10"],
]


def esperado_por_mes():
    meses = {}
    for _, data, _, produto, unidades in VENDAS:
        mes = date.fromisoformat(data).replace(day=1)
        p, u = int(produto), int(unidades)
        r, m, un = meses.get(mes, (Decimal(0), Decimal(0), 0))
        meses[mes] = (r + u * PRECO[p], m + u * (PRECO[p] - CUSTO[p]), un + u)
    return meses


def rodar(monkeypatch, tmp_path):
    raw_dir, db_path = apontar_pipeline(monkeypatch, tmp_path)
    escrever_raw(
        raw_dir, products=PRODUTOS, stores=LOJAS, sales=VENDAS, inventory=ESTOQUE
    )
    ingestao.main()
    transformacao.main()
    marts.main()
    return db_path


def test_receita_e_margem_por_mes(monkeypatch, tmp_path):
    db_path = rodar(monkeypatch, tmp_path)

    linhas = consultar(
        db_path,
        "SELECT mes, vendas, unidades, receita, margem, margem_pct "
        "FROM marts.receita_por_mes ORDER BY mes",
    )

    esperado = esperado_por_mes()
    assert [linha[0] for linha in linhas] == sorted(esperado)  # só meses com venda
    vendas_por_mes = {}
    for _, data, *_ in VENDAS:
        mes = date.fromisoformat(data).replace(day=1)
        vendas_por_mes[mes] = vendas_por_mes.get(mes, 0) + 1
    for mes, vendas, unidades, receita, margem, margem_pct in linhas:
        r, m, u = esperado[mes]
        assert (vendas, unidades, receita, margem) == (vendas_por_mes[mes], u, r, m)
        pct = (m / r).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        assert Decimal(str(margem_pct)) == pct


def test_soma_do_mart_bate_com_a_conta_total(monkeypatch, tmp_path):
    db_path = rodar(monkeypatch, tmp_path)
    total = sum(r for r, _, _ in esperado_por_mes().values())
    assert consultar(db_path, "SELECT sum(receita) FROM marts.receita_por_mes") == [
        (total,)
    ]
