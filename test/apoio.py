"""Apoio dos testes unitários: grava CSVs .csv.gz inventados e aponta o pipeline
para um diretório temporário. Nada aqui lê raw/ nem abre o toys.duckdb real."""

import csv
import gzip
from pathlib import Path

import duckdb

import ingestao
import marts
import transformacao

CABECALHOS = {
    "products": [
        "Product_ID",
        "Product_Name",
        "Product_Category",
        "Product_Cost",
        "Product_Price",
    ],
    "stores": [
        "Store_ID",
        "Store_Name",
        "Store_City",
        "Store_Location",
        "Store_Open_Date",
    ],
    "sales": ["Sale_ID", "Date", "Store_ID", "Product_ID", "Units"],
    "inventory": ["Store_ID", "Product_ID", "Stock_On_Hand"],
}

# Conjunto mínimo e válido, usado quando um teste só se importa com uma tabela.
# Cada teste substitui a tabela que está testando.
BASE = {
    "products": [
        # Produto 1: preço e custo no formato do arquivo real ("$" e espaço no fim).
        ["1", "Bola", "Sports & Outdoors", "$4.00 ", "$10.00 "],
    ],
    "stores": [
        # Loja 1: aberta antes de qualquer venda, cidade sem correção.
        ["1", "Loja Centro", "Guadalajara", "Downtown", "2010-05-01"],
    ],
    "sales": [
        # Uma venda válida, para a tabela de fatos não ficar vazia.
        ["1", "2017-01-15", "1", "1", "2"],
    ],
    "inventory": [
        # Estoque do único par loja × produto existente.
        ["1", "1", "5"],
    ],
}


def escrever_csv_gz(
    caminho: Path, cabecalho: list[str], linhas: list[list[str]]
) -> None:
    with gzip.open(caminho, "wt", newline="", encoding="utf-8") as f:
        escritor = csv.writer(f)
        escritor.writerow(cabecalho)
        escritor.writerows(linhas)


def escrever_raw(pasta: Path, **tabelas: list[list[str]]) -> None:
    """Grava os quatro CSVs; tabelas não informadas usam BASE."""
    pasta.mkdir(parents=True, exist_ok=True)
    for nome, cabecalho in CABECALHOS.items():
        escrever_csv_gz(
            pasta / f"{nome}.csv.gz", cabecalho, tabelas.get(nome, BASE[nome])
        )


def apontar_pipeline(monkeypatch, tmp_path: Path) -> tuple[Path, Path]:
    """Redireciona as constantes de caminho dos três scripts para tmp_path."""
    raw_dir = tmp_path / "raw"
    db_path = tmp_path / "teste.duckdb"
    monkeypatch.setattr(ingestao, "RAW_DIR", raw_dir)
    monkeypatch.setattr(ingestao, "DB_PATH", db_path)
    monkeypatch.setattr(transformacao, "DB_PATH", db_path)
    monkeypatch.setattr(marts, "DB_PATH", db_path)
    return raw_dir, db_path


def consultar(db_path: Path, sql: str) -> list[tuple]:
    with duckdb.connect(str(db_path), read_only=True) as con:
        return con.execute(sql).fetchall()
