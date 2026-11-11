"""Testes unitários de transformacao.py: raw inventada (via ingestao.main) -> refined."""

from datetime import date
from decimal import Decimal

import duckdb
import pytest
from apoio import BASE, apontar_pipeline, consultar, escrever_raw

import ingestao
import transformacao


def carregar(monkeypatch, tmp_path, **tabelas):
    raw_dir, db_path = apontar_pipeline(monkeypatch, tmp_path)
    escrever_raw(raw_dir, **tabelas)
    ingestao.main()
    transformacao.main()
    return db_path


def test_preco_e_custo_perdem_cifrao_e_espaco_e_viram_decimal(monkeypatch, tmp_path):
    produtos = [
        # Formato do arquivo real: "$" na frente e espaço no fim.
        ["1", "Bola", "Sports & Outdoors", "$4.00 ", "$10.00 "],
        # Sem espaço: o TRIM não pode ser o que faz a conversão funcionar.
        ["2", "Pião", "Toys", "$1.25", "$3.99"],
        # Espaço dos dois lados e valor com dois dígitos inteiros.
        ["3", "Robô", "Electronics", " $12.34 ", " $25.50 "],
    ]
    db_path = carregar(
        monkeypatch, tmp_path, products=produtos, inventory=[["1", "1", "5"]]
    )

    linhas = consultar(
        db_path,
        "SELECT product_id, product_cost, product_price FROM refined.products ORDER BY 1",
    )
    esperado = [
        (
            int(pid),
            Decimal(custo.strip().lstrip("$")),
            Decimal(preco.strip().lstrip("$")),
        )
        for pid, _, _, custo, preco in produtos
    ]
    assert linhas == esperado
    tipos = consultar(
        db_path,
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = 'refined' AND table_name = 'products' "
        "AND column_name IN ('product_cost', 'product_price') ORDER BY 1",
    )
    assert tipos == [
        ("product_cost", "DECIMAL(10,2)"),
        ("product_price", "DECIMAL(10,2)"),
    ]


def test_cuidad_vira_ciudad_e_outras_cidades_ficam_iguais(monkeypatch, tmp_path):
    lojas = [
        # O erro de digitação que a refined corrige.
        ["1", "Loja A", "Cuidad de Mexico", "Downtown", "2010-01-01"],
        # Cidade correta que começa com "Ciudad": não pode ser alterada.
        ["2", "Loja B", "Ciudad Victoria", "Airport", "2011-01-01"],
        # Cidade sem relação com a correção.
        ["3", "Loja C", "Guadalajara", "Residential", "2012-01-01"],
    ]
    db_path = carregar(monkeypatch, tmp_path, stores=lojas)

    cidades = consultar(
        db_path, "SELECT store_id, store_city FROM refined.stores ORDER BY 1"
    )
    assert cidades == [
        (1, "Ciudad de Mexico"),
        (2, "Ciudad Victoria"),
        (3, "Guadalajara"),
    ]
    assert consultar(
        db_path, "SELECT store_open_date FROM refined.stores WHERE store_id = 1"
    ) == [(date(2010, 1, 1),)]


def com_valor(tabela: str, coluna: int, valor: str) -> dict:
    """BASE com uma célula trocada."""
    linha = list(BASE[tabela][0])
    linha[coluna] = valor
    return {tabela: [linha]}


@pytest.mark.parametrize(
    "tabelas",
    [
        # Units não numérico: TRY_CAST viraria NULL; o CAST estrito tem de falhar.
        com_valor("sales", 4, "abc"),
        # Units zero: converte, mas viola o CHECK units > 0.
        com_valor("sales", 4, "0"),
        # Preço sem número depois de tirar "$" e espaço.
        com_valor("products", 4, "$abc "),
        # Data impossível.
        com_valor("stores", 4, "2017-13-45"),
        # Estoque por extenso.
        com_valor("inventory", 2, "dez"),
        # Venda de produto que não existe: viola a FK.
        com_valor("sales", 3, "99"),
    ],
    ids=[
        "units-texto",
        "units-zero",
        "preco-texto",
        "data-invalida",
        "estoque-texto",
        "fk-orfa",
    ],
)
def test_valor_invalido_faz_a_carga_falhar_sem_virar_nulo(
    monkeypatch, tmp_path, tabelas
):
    # Primeiro uma carga válida, para provar que a refined anterior sobrevive à falha.
    db_path = carregar(monkeypatch, tmp_path)
    antes = consultar(db_path, "SELECT * FROM refined.sales")

    escrever_raw(tmp_path / "raw", **tabelas)
    ingestao.main()  # a raw aceita qualquer texto
    with pytest.raises(duckdb.Error):
        transformacao.main()

    # Rollback: a refined continua a da carga válida, sem linha nova nem NULL.
    assert consultar(db_path, "SELECT * FROM refined.sales") == antes
    nulos = consultar(
        db_path,
        "SELECT count(*) FROM refined.sales "
        "WHERE sale_date IS NULL OR units IS NULL OR product_id IS NULL",
    )
    assert nulos == [(0,)]
