-- LidSense hydration monitor: MySQL / MariaDB schema
-- Import in phpMyAdmin: select your database -> Import -> choose this file -> Go.
-- All timestamps are UTC.

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS devices (
  id            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  device_id     VARCHAR(64)  NOT NULL UNIQUE,
  name          VARCHAR(128) NOT NULL DEFAULT '',
  api_key_hash  CHAR(64)     NOT NULL COMMENT 'SHA-256 of the device API key (hex)',
  last_seen     DATETIME(3)  NULL,
  status_json   TEXT         NULL COMMENT 'latest heartbeat from the Pi',
  created_at    DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS readings (
  id                BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  device_id         VARCHAR(64)  NOT NULL,
  seq               BIGINT UNSIGNED NOT NULL COMMENT 'per-device sequence number from the Pi',
  measured_at       DATETIME(3)  NOT NULL,
  received_at       DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  subject           VARCHAR(32)  NOT NULL DEFAULT '' COMMENT 'anonymised participant code',
  status            VARCHAR(32)  NULL COMMENT 'Hypohydrated / Euhydrated / Hyperhydrated',
  quality           VARCHAR(16)  NOT NULL COMMENT 'good / unstable / out_of_band / no_contact',
  resonant_freq_hz  DOUBLE       NULL,
  s11_db            DOUBLE       NULL,
  return_loss_db    DOUBLE       NULL,
  bandwidth_hz      DOUBLE       NULL,
  q_factor          DOUBLE       NULL,
  rl_spread_db      DOUBLE       NULL,
  contact_rms_db    DOUBLE       NULL,
  baseline_rl_db    DOUBLE       NULL,
  delta_db          DOUBLE       NULL COMMENT '+ = drier than personal baseline',
  alert             VARCHAR(32)  NULL,
  cal_id            VARCHAR(64)  NULL,
  UNIQUE KEY uq_device_seq (device_id, seq),
  KEY ix_device_time (device_id, measured_at),
  KEY ix_subject_time (subject, measured_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS sweeps (
  reading_id   BIGINT UNSIGNED PRIMARY KEY,
  device_id    VARCHAR(64) NOT NULL,
  measured_at  DATETIME(3) NOT NULL,
  start_hz     DOUBLE NOT NULL,
  stop_hz      DOUBLE NOT NULL,
  points       SMALLINT UNSIGNED NOT NULL,
  s11_db_json  MEDIUMTEXT NOT NULL COMMENT 'JSON array of S11 in dB',
  KEY ix_sweep_device_time (device_id, measured_at),
  CONSTRAINT fk_sweep_reading FOREIGN KEY (reading_id) REFERENCES readings(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS alerts (
  id           BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  device_id    VARCHAR(64) NOT NULL,
  local_id     BIGINT UNSIGNED NOT NULL,
  created_at   DATETIME(3) NOT NULL,
  event        VARCHAR(16) NOT NULL COMMENT 'raised / cleared / info',
  level        VARCHAR(32) NULL,
  message      VARCHAR(500) NOT NULL,
  subject      VARCHAR(32) NOT NULL DEFAULT '',
  UNIQUE KEY uq_alert (device_id, local_id),
  KEY ix_alert_time (device_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS baselines (
  id                BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  device_id         VARCHAR(64) NOT NULL,
  subject           VARCHAR(32) NOT NULL DEFAULT '',
  created_at        DATETIME(3) NOT NULL,
  return_loss_db    DOUBLE NOT NULL,
  resonant_freq_hz  DOUBLE NOT NULL,
  sd_db             DOUBLE NOT NULL,
  n                 INT NOT NULL,
  UNIQUE KEY uq_baseline (device_id, subject, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Handy view for phpMyAdmin browsing and Excel export
CREATE OR REPLACE VIEW v_readings AS
SELECT r.measured_at, r.device_id, r.subject, r.status, r.quality,
       ROUND(r.resonant_freq_hz / 1e9, 4) AS resonant_ghz,
       r.s11_db, r.return_loss_db, r.delta_db, r.alert
FROM readings r;
