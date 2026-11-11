-- Grão: uma linha por loja (store_id), ordenada pela posição no ranking de receita.
-- Premissas: receita = units × product_price; margem = units × (product_price − product_cost).
--   Usa o preço e o custo atuais do produto (o dataset não tem histórico de preço).
--   Lojas abertas em datas diferentes têm janelas de venda iguais (todas abriram antes de 2017).
WITH por_loja AS (
    SELECT
        s.store_id,
        sum(s.units)                                        AS unidades,
        sum(s.units * p.product_price)                      AS receita,
        sum(s.units * (p.product_price - p.product_cost))   AS margem
    FROM refined.sales s
    JOIN refined.products p USING (product_id)
    GROUP BY 1
)
SELECT
    rank() OVER (ORDER BY l.receita DESC)                   AS ranking_receita,
    rank() OVER (ORDER BY l.margem DESC)                    AS ranking_margem,
    st.store_id,
    st.store_name                                           AS loja,
    st.store_city                                           AS cidade,
    st.store_location                                       AS tipo_localizacao,
    l.unidades,
    l.receita,
    l.margem,
    round(l.margem / l.receita, 4)                          AS margem_pct
FROM por_loja l
JOIN refined.stores st USING (store_id)
ORDER BY ranking_receita, st.store_id
