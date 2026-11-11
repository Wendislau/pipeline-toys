-- Grão: uma linha por tipo de localização da loja (store_location).
-- Premissas: receita = units × product_price; margem = units × (product_price − product_cost).
--   Usa o preço e o custo atuais do produto (o dataset não tem histórico de preço).
--   receita_por_loja divide pelo número de lojas do tipo, pois os tipos têm quantidades diferentes.
SELECT
    st.store_location                                       AS tipo_localizacao,
    count(DISTINCT st.store_id)                             AS lojas,
    sum(s.units)                                            AS unidades,
    sum(s.units * p.product_price)                          AS receita,
    sum(s.units * (p.product_price - p.product_cost))       AS margem,
    round(sum(s.units * (p.product_price - p.product_cost))
          / sum(s.units * p.product_price), 4)              AS margem_pct,
    round(sum(s.units * p.product_price)
          / count(DISTINCT st.store_id), 2)                 AS receita_por_loja,
    round(sum(s.units * p.product_price)
          / sum(sum(s.units * p.product_price)) OVER (), 4) AS participacao_receita
FROM refined.sales s
JOIN refined.products p USING (product_id)
JOIN refined.stores st USING (store_id)
GROUP BY 1
ORDER BY receita DESC
