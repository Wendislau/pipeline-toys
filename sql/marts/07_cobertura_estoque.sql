-- Grão: uma linha por loja × produto presente em refined.inventory (1 linha por par do estoque).
--   Pares vendidos que não estão no estoque (ex.: Jenga em 24 lojas) ficam de fora;
--   ver specs/refined.md, seção de cobertura do inventory.
-- Janela: últimos 90 dias do dado, terminando na última data de venda (2018-09-30 na carga
--   real): sale_date entre fim − 89 dias e fim, inclusive.
-- Motivo: o estoque é uma foto do fim do período, sem data. A demanda que importa para
--   saber quanto ele dura é a recente, não a média de 2017–2018 inteiro.
-- Regras:
--   media_diaria_unidades = unidades vendidas na janela / 90 (dias sem venda contam como zero).
--   dias_cobertura = stock_on_hand / media_diaria_unidades; NULL quando a média é zero.
--   status: 'ruptura' se stock_on_hand = 0; 'critico' se dias_cobertura < 7; 'ok' no resto
--     (inclui estoque > 0 sem venda na janela, em que dias_cobertura é NULL).
WITH fim AS (
    SELECT max(sale_date) AS fim FROM refined.sales
),
vendas_janela AS (
    SELECT s.store_id, s.product_id, sum(s.units) AS unidades_90d
    FROM refined.sales s, fim
    WHERE s.sale_date BETWEEN fim.fim - 89 AND fim.fim
    GROUP BY ALL
),
cobertura AS (
    SELECT
        i.store_id,
        i.product_id,
        i.stock_on_hand,
        coalesce(v.unidades_90d, 0)                         AS unidades_90d,
        coalesce(v.unidades_90d, 0) / 90                    AS media_diaria_unidades
    FROM refined.inventory i
    LEFT JOIN vendas_janela v USING (store_id, product_id)
)
SELECT
    c.store_id,
    st.store_name                                           AS loja,
    st.store_city                                           AS cidade,
    st.store_location                                       AS tipo_localizacao,
    c.product_id,
    p.product_name                                          AS produto,
    p.product_category                                      AS categoria,
    c.stock_on_hand,
    c.unidades_90d,
    c.media_diaria_unidades,
    c.stock_on_hand / nullif(c.media_diaria_unidades, 0)    AS dias_cobertura,
    CASE
        WHEN c.stock_on_hand = 0 THEN 'ruptura'
        WHEN c.stock_on_hand / nullif(c.media_diaria_unidades, 0) < 7 THEN 'critico'
        ELSE 'ok'
    END                                                     AS status
FROM cobertura c
JOIN refined.stores st USING (store_id)
JOIN refined.products p USING (product_id)
ORDER BY c.store_id, c.product_id
