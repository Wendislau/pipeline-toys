"""Testes unitários de ingestao.py com CSVs inventados em tmp_path."""

import pytest
from apoio import CABECALHOS, apontar_pipeline, consultar, escrever_raw

import ingestao

PRODUTOS = [
    # Preço com "$" e espaço no fim: a ingestão deve guardar o texto intacto.
    ["1", "Bola", "Sports & Outdoors", "$4.00 ", "$10.00 "],
    # ID com zero à esquerda: só sobrevive se a coluna for lida como texto.
    ["007", "Pião", "Toys", "$1.50 ", "$3.00 "],
    # Valor não numérico: a ingestão não valida, só copia (quem valida é a refined).
    ["3", "Dado", "Games", "abc", "$2.00 "],
]


def test_cada_tabela_tem_as_mesmas_linhas_do_csv(monkeypatch, tmp_path):
    raw_dir, db_path = apontar_pipeline(monkeypatch, tmp_path)
    escrever_raw(raw_dir, products=PRODUTOS)

    ingestao.main()

    for tabela, cabecalho in CABECALHOS.items():
        esperado = PRODUTOS if tabela == "products" else None
        linhas = consultar(db_path, f"SELECT * FROM raw.{tabela}")
        if esperado is not None:
            assert sorted(linhas) == sorted(tuple(linha) for linha in esperado)
        colunas = consultar(
            db_path,
            "SELECT column_name, data_type FROM information_schema.columns "
            f"WHERE table_schema = 'raw' AND table_name = '{tabela}' ORDER BY ordinal_position",
        )
        assert colunas == [(c, "VARCHAR") for c in cabecalho]


def test_reexecucao_recria_do_zero_sem_acumular(monkeypatch, tmp_path):
    raw_dir, db_path = apontar_pipeline(monkeypatch, tmp_path)
    escrever_raw(raw_dir, products=PRODUTOS)
    ingestao.main()

    # Segunda carga com só o primeiro produto: se a ingestão acumulasse,
    # sobrariam as 3 linhas da primeira execução mais esta.
    escrever_raw(raw_dir, products=PRODUTOS[:1])
    ingestao.main()

    assert consultar(db_path, "SELECT * FROM raw.products") == [tuple(PRODUTOS[0])]


def test_arquivo_faltando_falha_sem_criar_banco(monkeypatch, tmp_path):
    raw_dir, db_path = apontar_pipeline(monkeypatch, tmp_path)
    escrever_raw(raw_dir)
    (raw_dir / "stores.csv.gz").unlink()  # tira um dos quatro arquivos obrigatórios

    with pytest.raises(FileNotFoundError, match="stores.csv.gz"):
        ingestao.main()
    assert not db_path.exists()
