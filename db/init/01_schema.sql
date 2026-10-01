-- =====================================================================
--  BrandPulse :: esquema del warehouse de sentimiento
--  Postgres 16 - inicializado automaticamente por docker-compose
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. Hecho principal: una fila por mencion de la marca
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mentions (
    mention_id        TEXT PRIMARY KEY,
    ts                TIMESTAMPTZ NOT NULL,
    brand             TEXT NOT NULL,
    platform          TEXT NOT NULL,
    author            TEXT NOT NULL,
    author_followers  INTEGER NOT NULL DEFAULT 0,
    text              TEXT NOT NULL,
    lang              TEXT NOT NULL DEFAULT 'es',
    hashtags          TEXT[] NOT NULL DEFAULT '{}',
    keywords          TEXT[] NOT NULL DEFAULT '{}',
    sentiment         TEXT NOT NULL CHECK (sentiment IN ('POSITIVO','NEUTRAL','NEGATIVO')),
    score             DOUBLE PRECISION NOT NULL,
    confidence        DOUBLE PRECISION NOT NULL,
    dnc_comparisons   INTEGER NOT NULL,
    dnc_levels        INTEGER NOT NULL,
    sort_comparisons  INTEGER NOT NULL,
    expected          TEXT CHECK (expected IN ('POSITIVO','NEUTRAL','NEGATIVO')),
    likes             INTEGER NOT NULL DEFAULT 0,
    shares            INTEGER NOT NULL DEFAULT 0,
    processed_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mentions_ts        ON mentions (ts DESC);
CREATE INDEX IF NOT EXISTS idx_mentions_sentiment ON mentions (sentiment);
CREATE INDEX IF NOT EXISTS idx_mentions_platform  ON mentions (platform);
CREATE INDEX IF NOT EXISTS idx_mentions_author    ON mentions (author);

-- ---------------------------------------------------------------------
-- 2. Serie temporal de sentimiento por minuto (reemplazo idempotente)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sentiment_buckets (
    bucket     TIMESTAMPTZ NOT NULL,
    sentiment  TEXT NOT NULL,
    mentions   BIGINT NOT NULL,
    PRIMARY KEY (bucket, sentiment)
);

-- ---------------------------------------------------------------------
-- 3. Instantanea del grafo de co-ocurrencia (marca / usuario / hashtag /
--    palabra clave). Se recalcula y reemplaza por completo en cada
--    micro-lote para que la vista siempre sea consistente.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS graph_nodes (
    node_id     TEXT PRIMARY KEY,
    label       TEXT NOT NULL CHECK (label IN ('MARCA','USUARIO','HASHTAG','PALABRA','PLATAFORMA')),
    name        TEXT NOT NULL,
    weight      BIGINT NOT NULL,
    pos_count   BIGINT NOT NULL DEFAULT 0,
    neu_count   BIGINT NOT NULL DEFAULT 0,
    neg_count   BIGINT NOT NULL DEFAULT 0,
    sentiment   TEXT NOT NULL,
    mentions    BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS graph_edges (
    edge_id   TEXT PRIMARY KEY,
    src       TEXT NOT NULL,
    dst       TEXT NOT NULL,
    rel       TEXT NOT NULL,
    weight    BIGINT NOT NULL,
    sentiment TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_graph_edges_src ON graph_edges (src);
CREATE INDEX IF NOT EXISTS idx_graph_edges_dst ON graph_edges (dst);

-- ---------------------------------------------------------------------
-- 4. Medicion empirica de la complejidad del algoritmo
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS complexity_stats (
    batch_index        BIGINT PRIMARY KEY,
    processed_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    messages           BIGINT NOT NULL,
    total_tokens       BIGINT NOT NULL,
    dnc_comparisons    BIGINT NOT NULL,
    dnc_levels         BIGINT NOT NULL,
    sort_comparisons   BIGINT NOT NULL,
    theoretical_min    BIGINT NOT NULL,
    merge_operations   BIGINT NOT NULL
);

-- ---------------------------------------------------------------------
-- 5. Estado del pipeline (traza / checkpoint logico)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pipeline_state (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    brand         TEXT NOT NULL,
    last_batch    BIGINT NOT NULL DEFAULT -1,
    last_updated  TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO pipeline_state (id, brand)
VALUES (1, 'Nike')
ON CONFLICT (id) DO NOTHING;

-- ---------------------------------------------------------------------
-- 6. Vista de exactitud: compara el sentimiento calculado por el
--    algoritmo contra la etiqueta real del dato sintetico.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_accuracy AS
SELECT
    COALESCE(expected, 'DESCONOCIDO')            AS clase_real,
    COALESCE(sentiment, 'DESCONOCIDO')           AS clase_predicha,
    COUNT(*)                                     AS supportive,
    ROUND(100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0), 2) AS pct
FROM mentions
WHERE expected IS NOT NULL
GROUP BY 1, 2;

CREATE OR REPLACE VIEW v_kpis AS
SELECT
    COUNT(*)                                            AS total,
    COUNT(*) FILTER (WHERE sentiment = 'POSITIVO')      AS positivos,
    COUNT(*) FILTER (WHERE sentiment = 'NEUTRAL')       AS neutrales,
    COUNT(*) FILTER (WHERE sentiment = 'NEGATIVO')      AS negativos,
    COUNT(*) FILTER (WHERE expected IS NOT NULL)        AS etiquetados,
    COUNT(*) FILTER (WHERE expected IS NOT NULL
                       AND expected = sentiment)        AS correctos,
    ROUND(AVG(score)::numeric, 4)                       AS score_promedio,
    ROUND(AVG(confidence)::numeric, 4)                  AS confianza_promedio,
    ROUND(AVG(dnc_comparisons)::numeric, 1)             AS comparaciones_promedio,
    COUNT(DISTINCT author)                              AS autores,
    COUNT(DISTINCT platform)                            AS plataformas
FROM mentions;