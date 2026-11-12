"""Testes unitários dos marts 01 (receita_por_mes) e 07 (cobertura_estoque) com tabelas inventadas."""

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

import pytest
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


# --- Mart 07: cobertura de estoque ----------------------------------------------

FIM = date(2018, 9, 30)  # última venda do dado inventado; define o fim da janela
INICIO_JANELA = FIM - timedelta(days=89)  # 90 dias contando o próprio fim: 2018-07-03

PRODUTOS_ESTOQUE = [
    ["1", "Ruptura", "Toys", "$1.00 ", "$2.00 "],
    ["2", "Critico", "Toys", "$1.00 ", "$2.00 "],
    ["3", "Limite", "Toys", "$1.00 ", "$2.00 "],
    ["4", "Borda", "Games", "$1.00 ", "$2.00 "],
    ["5", "Parado", "Games", "$1.00 ", "$2.00 "],
    ["6", "ForaEstoque", "Games", "$1.00 ", "$2.00 "],
    ["7", "ForaAntigo", "Games", "$1.00 ", "$2.00 "],
]
LOJA_ESTOQUE = [["1", "Loja A", "Guadalajara", "Downtown", "2010-01-01"]]
ESTOQUE_07 = [
    # Produto 1: estoque zero com venda recente -> 'ruptura' (zero vence qualquer média).
    ["1", "1", "0"],
    # Produto 2: 6 unidades para média de 1/dia -> 6 dias -> 'critico'.
    ["1", "2", "6"],
    # Produto 3: 7 unidades para média de 1/dia -> exatamente 7 dias -> 'ok' (regra é < 7).
    ["1", "3", "7"],
    # Produto 4: testa as bordas da janela (ver vendas) -> 100 dias -> 'ok'.
    ["1", "4", "50"],
    # Produto 5: estoque sem venda na janela -> média zero, dias NULL, 'sem demanda'.
    ["1", "5", "5"],
    # Produto 6 fica fora do estoque de propósito: vende na janela -> 'sem registro',
    #   com stock_on_hand NULL (a ausência não vira zero).
    # Produto 7 também fica fora do estoque, mas só vendeu antes da janela -> não aparece.
]
VENDAS_07 = [
    # (sale_id, data, loja, produto, unidades)
    ["1", "2018-08-15", "1", "1", "90"],  # 90 na janela -> média 1/dia
    ["2", "2018-08-15", "1", "2", "90"],  # idem
    ["3", "2018-08-15", "1", "3", "90"],  # idem
    [
        "4",
        "2018-07-03",
        "1",
        "4",
        "45",
    ],  # primeiro dia da janela: conta (média 0,5/dia)
    [
        "5",
        "2018-07-02",
        "1",
        "4",
        "900",
    ],  # véspera da janela: não conta (senão viraria crítico)
    [
        "6",
        "2017-03-10",
        "1",
        "5",
        "20",
    ],  # venda antiga: fora da janela, média continua zero
    ["7", "2018-09-30", "1", "6", "1"],  # define o fim do dado; par fora do estoque
    ["8", "2018-09-01", "1", "6", "8"],  # par fora do estoque: 9 unidades na janela
    ["9", "2017-05-01", "1", "7", "30"],  # fora do estoque e fora da janela: não entra
]


def esperado_cobertura():
    """Regra do mart refeita em Python a partir das linhas inventadas."""

    def unidades_janela(produto):
        return sum(
            int(u)
            for _, data, _, p, u in VENDAS_07
            if p == produto and INICIO_JANELA <= date.fromisoformat(data) <= FIM
        )

    esperado = {}
    for _, produto, estoque in ESTOQUE_07:
        media = unidades_janela(produto) / 90
        dias = int(estoque) / media if media else None
        if int(estoque) == 0:
            status = "ruptura"
        elif media == 0:
            status = "sem demanda"
        elif dias < 7:
            status = "critico"
        else:
            status = "ok"
        esperado[int(produto)] = (int(estoque), media, dias, status)
    # Pares vendidos na janela e ausentes do estoque: estoque e dias NULL, 'sem registro'.
    no_estoque = {p for _, p, _ in ESTOQUE_07}
    for produto, *_ in PRODUTOS_ESTOQUE:
        if produto not in no_estoque and unidades_janela(produto):
            esperado[int(produto)] = (
                None,
                unidades_janela(produto) / 90,
                None,
                "sem registro",
            )
    return esperado


def test_cobertura_estoque_status_e_janela_de_90_dias(monkeypatch, tmp_path):
    raw_dir, db_path = apontar_pipeline(monkeypatch, tmp_path)
    escrever_raw(
        raw_dir,
        products=PRODUTOS_ESTOQUE,
        stores=LOJA_ESTOQUE,
        sales=VENDAS_07,
        inventory=ESTOQUE_07,
    )
    ingestao.main()
    transformacao.main()
    marts.main()

    linhas = consultar(
        db_path,
        "SELECT product_id, stock_on_hand, media_diaria_unidades, dias_cobertura, status "
        "FROM marts.cobertura_estoque ORDER BY product_id",
    )
    obtido = {
        pid: (estoque, media, dias, status)
        for pid, estoque, media, dias, status in linhas
    }

    esperado = esperado_cobertura()
    # Produto 6 (sem registro, vendeu na janela) entra; produto 7 (só venda antiga) não.
    assert obtido.keys() == esperado.keys() == {1, 2, 3, 4, 5, 6}
    for pid, (estoque, media, dias, status) in esperado.items():
        o_estoque, o_media, o_dias, o_status = obtido[pid]
        assert (o_estoque, o_status) == (estoque, status), pid
        assert o_media == pytest.approx(media), pid
        assert o_dias == (None if dias is None else pytest.approx(dias)), pid
    # Todos os status estão cobertos pelo dado inventado.
    assert {s for *_, s in esperado.values()} == {
        "ruptura",
        "critico",
        "ok",
        "sem demanda",
        "sem registro",
    }
    assert obtido[6][0] is None and obtido[6][2] is None  # sem registro: NULL, não zero
