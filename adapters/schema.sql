-- Archivio dei segnali (D-007). Orari in testo ISO 8601 UTC.
-- Le colonne annullabili senza valore oggi (input del ciclo, versione del codice, feature, veto ombra)
-- vengono riempite dall'orchestrazione (P3.25) e dal revisore offline (P5.08).

CREATE TABLE IF NOT EXISTS cycles (
    cycle_id            INTEGER PRIMARY KEY,
    symbol              TEXT NOT NULL,
    candle_close_utc    TEXT NOT NULL,
    candle_close_server TEXT,
    code_version        TEXT,
    config_hash         TEXT,
    input_json          TEXT,
    input_hash          TEXT,
    started_at          TEXT NOT NULL,
    finished_at         TEXT,
    status              TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'done', 'error')),
    error               TEXT,
    UNIQUE (symbol, candle_close_utc)
);

CREATE TABLE IF NOT EXISTS llm_calls (
    call_id        INTEGER PRIMARY KEY,
    cycle_id       INTEGER NOT NULL REFERENCES cycles (cycle_id),
    role           TEXT NOT NULL,
    provider       TEXT,
    model          TEXT NOT NULL,
    model_digest   TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    prompt_text    TEXT,
    temperature    REAL NOT NULL CHECK (temperature = 0),
    seed           INTEGER,
    response_raw   TEXT,
    parsed_json    TEXT,
    schema_valid   INTEGER NOT NULL CHECK (schema_valid IN (0, 1)),
    attempts       INTEGER NOT NULL CHECK (attempts >= 1),
    latency_ms     REAL,
    tokens_in      INTEGER,
    tokens_out     INTEGER,
    cost_eur       REAL,
    error          TEXT
);

CREATE TABLE IF NOT EXISTS candidates (
    candidate_id  INTEGER PRIMARY KEY,
    cycle_id      INTEGER NOT NULL REFERENCES cycles (cycle_id),
    variant       TEXT NOT NULL,
    direction     TEXT NOT NULL CHECK (direction IN ('BUY', 'SELL')),
    entry_ref     REAL NOT NULL,
    sl            REAL NOT NULL,
    tp            REAL NOT NULL,
    d_sl          REAL NOT NULL,
    d_tp          REAL NOT NULL,
    cost_pips     REAL NOT NULL,
    p0            REAL,
    p             REAL NOT NULL CHECK (p > 0 AND p < 1),
    p_star        REAL NOT NULL,
    p5            REAL,
    ev            REAL NOT NULL,
    ev5           REAL NOT NULL,
    gate_passed   INTEGER CHECK (gate_passed IN (0, 1)),
    veto_shadow   TEXT,
    final_action  TEXT NOT NULL CHECK (final_action IN ('TRADE', 'HOLD')),
    lot           REAL,
    hold_reason   TEXT,
    features_json TEXT,
    UNIQUE (cycle_id, variant)
);

CREATE TABLE IF NOT EXISTS executions (
    candidate_id INTEGER PRIMARY KEY REFERENCES candidates (candidate_id),
    mode         TEXT NOT NULL CHECK (mode IN ('sim', 'mt5')),
    accepted     INTEGER NOT NULL CHECK (accepted IN (0, 1)),
    ticket       INTEGER,
    lots         REAL NOT NULL,
    fill_price   REAL,
    spread       REAL,
    slippage     REAL,
    commission   REAL,
    swap         REAL,
    reason       TEXT
);

CREATE TABLE IF NOT EXISTS outcomes (
    candidate_id INTEGER PRIMARY KEY REFERENCES candidates (candidate_id),
    resolution   TEXT NOT NULL CHECK (resolution IN ('TP', 'SL', 'TIMEOUT')),
    exit_utc     TEXT NOT NULL,
    exit_price   REAL,
    r_gross      REAL,
    r_net        REAL,
    resolved_by  TEXT NOT NULL CHECK (resolved_by IN ('virtuale', 'broker'))
);
