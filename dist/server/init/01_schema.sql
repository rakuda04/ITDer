-- =============================================================
-- Itder Pipeline — PostgreSQL Schema
-- Auto-runs on first docker compose up
-- =============================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- -------------------------------------------------------------
-- 1. devices
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS devices (
    device_id       UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    hostname        TEXT        NOT NULL UNIQUE,
    windows_version TEXT,
    enrolled_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at    TIMESTAMPTZ,
    active          BOOLEAN     NOT NULL DEFAULT TRUE
);

-- -------------------------------------------------------------
-- 2. pipeline_runs
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id           BIGSERIAL   PRIMARY KEY,
    device_id        UUID        NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
    started_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at      TIMESTAMPTZ,
    status           TEXT        NOT NULL DEFAULT 'running'
                     CHECK (status IN ('running', 'success', 'failed')),
    error_message    TEXT,
    events_collected INTEGER,
    events_inserted  INTEGER
);

CREATE INDEX IF NOT EXISTS pipeline_runs_device ON pipeline_runs (device_id, started_at DESC);

-- -------------------------------------------------------------
-- 3. daily_features
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS daily_features (
    id                              BIGSERIAL   PRIMARY KEY,
    device_id                       UUID        NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
    run_id                          BIGINT      REFERENCES pipeline_runs(run_id) ON DELETE SET NULL,
    username                        TEXT        NOT NULL,
    feature_date                    DATE        NOT NULL,

    total_active_minutes_day        REAL,
    after_hours_session_count       INTEGER,
    weekend_session_flag            SMALLINT,
    logon_count_zscore              REAL,
    logon_count_zscore_has_baseline SMALLINT,

    usb_count                       REAL,
    usb_after_hours_flag            SMALLINT,
    usb_on_weekend_flag             SMALLINT,
    usb_device_diversity_monthly    REAL,
    usb_count_zscore                REAL,
    usb_count_zscore_has_baseline   SMALLINT,

    job_site_visits_flag            SMALLINT,
    job_search_plus_usb_week        SMALLINT,

    inserted_at                     TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (device_id, username, feature_date)
);

CREATE INDEX IF NOT EXISTS daily_features_device_date   ON daily_features (device_id, feature_date DESC);
CREATE INDEX IF NOT EXISTS daily_features_username_date ON daily_features (username, feature_date DESC);

-- -------------------------------------------------------------
-- 4. daily_scores
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS daily_scores (
    id                  BIGSERIAL   PRIMARY KEY,
    device_id           UUID        NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
    run_id              BIGINT      REFERENCES pipeline_runs(run_id) ON DELETE SET NULL,
    username            TEXT        NOT NULL,
    score_date          DATE        NOT NULL,

    supervised_score    REAL,
    unsupervised_score  REAL,
    combined_risk_score REAL,

    iso_prediction      SMALLINT,
    iso_score           REAL,
    iso_score_norm      REAL,
    lof_prediction      SMALLINT,
    lof_score           REAL,
    lof_score_norm      REAL,

    flagged_by_both     SMALLINT,
    above_threshold     SMALLINT,
    is_synthetic        SMALLINT,

    inserted_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (device_id, username, score_date, run_id)
);

CREATE INDEX IF NOT EXISTS daily_scores_device_date     ON daily_scores (device_id, score_date DESC);
CREATE INDEX IF NOT EXISTS daily_scores_username        ON daily_scores (username, score_date DESC);
CREATE INDEX IF NOT EXISTS daily_scores_above_threshold ON daily_scores (above_threshold) WHERE above_threshold = 1;

-- -------------------------------------------------------------
-- 5. user_risk
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_risk (
    id                   BIGSERIAL   PRIMARY KEY,
    device_id            UUID        NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
    run_id               BIGINT      REFERENCES pipeline_runs(run_id) ON DELETE SET NULL,
    username             TEXT        NOT NULL,

    rank                 INTEGER,
    is_synthetic         SMALLINT,
    days_above_threshold INTEGER,
    final_risk_score     REAL,
    supervised_max       REAL,
    supervised_mean      REAL,
    unsupervised_max     REAL,
    unsupervised_mean    REAL,
    iso_score_norm_mean  REAL,
    lof_score_norm_mean  REAL,
    days_flagged_iso     INTEGER,
    days_flagged_lof     INTEGER,
    days_flagged_both    INTEGER,
    total_days           INTEGER,
    peak_date            DATE,
    composite_rank_score REAL,

    inserted_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (device_id, username, run_id)
);

CREATE INDEX IF NOT EXISTS user_risk_device_run  ON user_risk (device_id, run_id DESC);
CREATE INDEX IF NOT EXISTS user_risk_risk_score  ON user_risk (final_risk_score DESC);

-- -------------------------------------------------------------
-- 6. shap_values
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS shap_values (
    id                              BIGSERIAL   PRIMARY KEY,
    device_id                       UUID        NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
    run_id                          BIGINT      REFERENCES pipeline_runs(run_id) ON DELETE SET NULL,
    username                        TEXT        NOT NULL,
    score_date                      DATE        NOT NULL,

    after_hours_session_count       REAL,
    weekend_session_flag            REAL,
    logon_count_zscore              REAL,
    logon_count_zscore_has_baseline REAL,
    usb_count                       REAL,
    usb_after_hours_flag            REAL,
    usb_on_weekend_flag             REAL,
    usb_device_diversity_monthly    REAL,
    usb_count_zscore                REAL,
    job_site_visits_flag            REAL,
    job_search_plus_usb_week        REAL,

    inserted_at                     TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (device_id, username, score_date, run_id)
);

CREATE INDEX IF NOT EXISTS shap_values_username ON shap_values (username, score_date DESC);

-- -------------------------------------------------------------
-- 6. View — latest risk per user across all devices
-- -------------------------------------------------------------
CREATE OR REPLACE VIEW v_latest_user_risk AS
SELECT DISTINCT ON (ur.username)
    ur.username,
    ur.final_risk_score,
    ur.composite_rank_score,
    ur.rank,
    ur.days_above_threshold,
    ur.days_flagged_both,
    ur.peak_date,
    d.hostname,
    pr.started_at AS last_run_at
FROM user_risk ur
JOIN devices       d  ON d.device_id = ur.device_id
JOIN pipeline_runs pr ON pr.run_id   = ur.run_id
WHERE ur.is_synthetic = 0
ORDER BY ur.username, pr.started_at DESC;