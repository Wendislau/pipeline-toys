-- Grão: uma linha por produto (product_id), ordenada da maior para a menor receita.
-- Premissas: receita = units × product_price; margem = units × (product_price − product_cost).
--   Usa o preço e o custo atuais do produto (o dataset não tem histórico de preço).
--   Curva ABC pela receita acumulada ANTES do produto: A até 80%, B até 95%, C o resto.
--   Assim o produto que cruza a linha dos 80% ainda entra na classe A.
WITH por_produto AS (
    SELECT
        p.product_id,
        p.product_name,
        p.product_category,
        sum(s.units)                                        AS unidades,
        sum(s.units * p.product_price)                      AS receita,
        sum(s.units * (p.product_price - p.product_cost))   AS margem
    FROM refined.sales s
    JOIN refined.products p USING (product_id)
    GROUP BY 1, 2, 3
),
acumulado AS (
    SELECT
        *,
        row_number() OVER w                                 AS posicao,
        sum(receita) OVER w                                 AS receita_acumulada,
        sum(receita) OVER ()                                AS receita_total
    FROM por_produto
    WINDOW w AS (ORDER BY receita DESC, product_id
                 ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
)
SELECT
    posicao,
    product_id,
    product_name                                            AS produto,
    product_category                                        AS categoria,
    unidades,
    receita,
    margem,
    round(receita / receita_total, 4)                       AS participacao_receita,
    receita_acumulada,
    round(receita_acumulada / receita_total, 4)             AS participacao_acumulada,
    CASE
        WHEN (receita_acumulada - receita) / receita_total < 0.80 THEN 'A'
        WHEN (receita_acumulada - receita) / receita_total < 0.95 THEN 'B'
        ELSE 'C'
    END                                                     AS classe_abc
FROM acumulado
ORDER BY posicao
