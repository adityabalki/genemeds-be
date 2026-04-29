-- =============================================================
-- Genemeds — Full Database Schema
-- Run once on RDS: psql -f schema.sql
-- All tables live in the core schema.
-- =============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE SCHEMA IF NOT EXISTS core;

-- =============================================================
-- AUTH TABLE SEQUENCES  (human-readable role IDs)
-- =============================================================

CREATE SEQUENCE IF NOT EXISTS core.hcp_id_seq          START 1 INCREMENT 1;
CREATE SEQUENCE IF NOT EXISTS core.receptionist_id_seq START 1 INCREMENT 1;
CREATE SEQUENCE IF NOT EXISTS core.lab_id_seq          START 1 INCREMENT 1;
CREATE SEQUENCE IF NOT EXISTS core.admin_id_seq        START 1 INCREMENT 1;
CREATE SEQUENCE IF NOT EXISTS core.patient_auth_id_seq START 1 INCREMENT 1;

-- =============================================================
-- AUTH TABLES
-- =============================================================

CREATE TABLE IF NOT EXISTS core.admins (
    id              SERIAL      PRIMARY KEY,
    admin_id        VARCHAR(20) UNIQUE,              -- ADM-00001
    email           TEXT        UNIQUE NOT NULL,
    password_hash   TEXT        NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS core.hcps (
    id                   SERIAL      PRIMARY KEY,
    hcp_id               VARCHAR(20) UNIQUE,          -- HCP-00001
    full_name            TEXT        NOT NULL,
    email                TEXT        UNIQUE NOT NULL,
    password_hash        TEXT        NOT NULL,
    mobile               TEXT,
    degree               TEXT,
    specialisation       TEXT,
    experience           TEXT,
    hospital             TEXT,
    clinic_code          TEXT,                        -- optional clinic association
    registration_number  TEXT        UNIQUE,
    council              TEXT,
    registration_year    TEXT,
    is_verified          BOOLEAN     DEFAULT FALSE,
    created_at           TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS core.receptionists (
    id                SERIAL      PRIMARY KEY,
    receptionist_id   VARCHAR(20) UNIQUE,             -- REC-00001
    full_name         TEXT        NOT NULL,
    email             TEXT        UNIQUE NOT NULL,
    password_hash     TEXT        NOT NULL,
    mobile            TEXT,
    clinic            TEXT,
    clinic_code       TEXT        NOT NULL,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS core.labs (
    id              SERIAL      PRIMARY KEY,
    lab_id          VARCHAR(20) UNIQUE,               -- LAB-00001
    lab_name        TEXT        NOT NULL,
    contact_person  TEXT,
    email           TEXT        UNIQUE NOT NULL,
    password_hash   TEXT        NOT NULL,
    mobile          TEXT,
    license_id      TEXT        UNIQUE,
    address         TEXT,
    city            TEXT,
    state           TEXT,
    pincode         TEXT,
    is_verified     BOOLEAN     DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Auth-only patients table (login accounts)
CREATE TABLE IF NOT EXISTS core.patients (
    id              SERIAL      PRIMARY KEY,
    patient_auth_id VARCHAR(20) UNIQUE,               -- PAT-00001
    full_name       TEXT        NOT NULL,
    email           TEXT        UNIQUE NOT NULL,
    password_hash   TEXT        NOT NULL,
    mobile          TEXT,
    dob             DATE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hcps_email          ON core.hcps(email);
CREATE INDEX IF NOT EXISTS idx_hcps_clinic_code    ON core.hcps(clinic_code);
CREATE INDEX IF NOT EXISTS idx_receptionists_email ON core.receptionists(email);
CREATE INDEX IF NOT EXISTS idx_labs_email          ON core.labs(email);
CREATE INDEX IF NOT EXISTS idx_patients_email      ON core.patients(email);
CREATE INDEX IF NOT EXISTS idx_admins_email        ON core.admins(email);

-- =============================================================
-- RECEPTIONIST OPERATIONAL TABLES
-- =============================================================

-- Sequence for human-readable patient IDs: PAT-00001, PAT-00002 …
CREATE SEQUENCE IF NOT EXISTS core.patient_id_seq START 1 INCREMENT 1;

-- Sequence for human-readable appointment IDs: APT-00001, APT-00002 …
CREATE SEQUENCE IF NOT EXISTS core.appointment_id_seq START 1 INCREMENT 1;

-- Clinical patient registrations (distinct from core.patients auth table)
CREATE TABLE IF NOT EXISTS core.patient_registrations (
    id                   BIGSERIAL   PRIMARY KEY,
    patient_id           VARCHAR(20) UNIQUE NOT NULL,   -- PAT-XXXXX
    clinic_code          VARCHAR(50) NOT NULL,
    full_name            VARCHAR(200) NOT NULL,
    mobile               VARCHAR(15) NOT NULL,
    email                VARCHAR(200),
    date_of_birth        DATE,
    gender               VARCHAR(30),
    city                 VARCHAR(100),
    visit_type           VARCHAR(20) DEFAULT 'First Visit',
    chief_complaint      TEXT,
    ongoing_treatment    TEXT,
    known_allergies      TEXT,
    past_medical_history TEXT,
    family_history       TEXT,
    gene_test_status     VARCHAR(20) DEFAULT 'not_done',  -- not_done / uploaded / processed
    token_number         VARCHAR(10),
    registered_by        INTEGER NOT NULL,               -- core.receptionists.id
    created_at           TIMESTAMPTZ DEFAULT NOW(),
    updated_at           TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pat_reg_clinic_mobile  ON core.patient_registrations (clinic_code, mobile);
CREATE INDEX IF NOT EXISTS idx_pat_reg_clinic_created ON core.patient_registrations (clinic_code, created_at);

-- Per-visit vitals
CREATE TABLE IF NOT EXISTS core.patient_vitals (
    id           BIGSERIAL PRIMARY KEY,
    patient_id   BIGINT    NOT NULL REFERENCES core.patient_registrations (id),
    bp_systolic  INTEGER,
    bp_diastolic INTEGER,
    weight_kg    NUMERIC(5, 2),
    o2_level     NUMERIC(4, 1),
    notes        TEXT,
    recorded_by  INTEGER NOT NULL,                       -- core.receptionists.id
    recorded_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_vitals_patient ON core.patient_vitals (patient_id);

-- Uploaded files (lab reports, gene tests)
CREATE TABLE IF NOT EXISTS core.patient_documents (
    id                BIGSERIAL PRIMARY KEY,
    patient_id        BIGINT    NOT NULL REFERENCES core.patient_registrations (id),
    s3_key            TEXT      NOT NULL,
    file_type         VARCHAR(30) NOT NULL,              -- gene_test / lab_report
    original_filename TEXT,
    content_type      VARCHAR(100),
    uploaded_by       INTEGER NOT NULL,                  -- core.receptionists.id
    uploaded_at       TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_docs_patient ON core.patient_documents (patient_id);

-- DPDP Act 2023 consent records
CREATE TABLE IF NOT EXISTS core.patient_consents (
    id                   BIGSERIAL PRIMARY KEY,
    patient_id           BIGINT    NOT NULL REFERENCES core.patient_registrations (id),
    consent_type         VARCHAR(50) NOT NULL,           -- genetic_data_processing
    consented_by_role    VARCHAR(30) NOT NULL,           -- receptionist / lab / hcp
    consented_by_user_id INTEGER NOT NULL,
    clinic_code          VARCHAR(50) NOT NULL,
    ip_address           VARCHAR(45),
    created_at           TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_consents_patient ON core.patient_consents (patient_id);

-- Appointments
CREATE TABLE IF NOT EXISTS core.appointments (
    id                    BIGSERIAL   PRIMARY KEY,
    appointment_ref       VARCHAR(20) UNIQUE NOT NULL,   -- APT-XXXXX
    patient_id            BIGINT      NOT NULL REFERENCES core.patient_registrations (id),
    hcp_id                INTEGER     NOT NULL,          -- core.hcps.id
    clinic_code           VARCHAR(50) NOT NULL,
    appointment_datetime  TIMESTAMPTZ NOT NULL,
    slot_duration_minutes INTEGER DEFAULT 15,
    status                VARCHAR(30) DEFAULT 'scheduled',  -- scheduled/waiting/in_consultation/done/cancelled
    token_number          VARCHAR(10),
    visit_type            VARCHAR(20) DEFAULT 'First Visit',
    booked_by             INTEGER NOT NULL,              -- core.receptionists.id
    notes                 TEXT,
    created_at            TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (hcp_id, appointment_datetime)
);
CREATE INDEX IF NOT EXISTS idx_appt_clinic_dt ON core.appointments (clinic_code, appointment_datetime);

-- One active appointment per patient per doctor per day (cancelled doesn't count)
CREATE UNIQUE INDEX IF NOT EXISTS uix_appt_patient_hcp_day
    ON core.appointments (patient_id, hcp_id, CAST(appointment_datetime AT TIME ZONE 'Asia/Kolkata' AS date))
    WHERE status != 'cancelled';

-- Weekly HCP availability schedule
CREATE TABLE IF NOT EXISTS core.hcp_availability (
    id                    BIGSERIAL   PRIMARY KEY,
    hcp_id                INTEGER     NOT NULL,          -- core.hcps.id
    clinic_code           VARCHAR(50) NOT NULL,
    day_of_week           INTEGER     NOT NULL,          -- 0=Monday … 6=Sunday
    start_time            TIME        NOT NULL,
    end_time              TIME        NOT NULL,
    slot_duration_minutes INTEGER DEFAULT 15,
    is_active             BOOLEAN DEFAULT TRUE,
    created_at            TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (hcp_id, clinic_code, day_of_week)
);
CREATE INDEX IF NOT EXISTS idx_hcp_avail ON core.hcp_availability (hcp_id, clinic_code);

-- =============================================================
-- INCREMENTAL MIGRATION (apply to existing DB without data loss)
-- Run each block once — all statements are idempotent.
-- =============================================================

-- Auth table display-ID columns
ALTER TABLE core.hcps          ADD COLUMN IF NOT EXISTS hcp_id          VARCHAR(20) UNIQUE;
ALTER TABLE core.receptionists ADD COLUMN IF NOT EXISTS receptionist_id  VARCHAR(20) UNIQUE;
ALTER TABLE core.labs          ADD COLUMN IF NOT EXISTS lab_id           VARCHAR(20) UNIQUE;
ALTER TABLE core.admins        ADD COLUMN IF NOT EXISTS admin_id         VARCHAR(20) UNIQUE;
ALTER TABLE core.patients      ADD COLUMN IF NOT EXISTS patient_auth_id  VARCHAR(20) UNIQUE;

-- Vitals notes
ALTER TABLE core.patient_vitals ADD COLUMN IF NOT EXISTS notes TEXT;

-- Appointment meaningful ref (if upgrading from UUID schema)
ALTER TABLE core.appointments ADD COLUMN IF NOT EXISTS appointment_ref VARCHAR(20) UNIQUE;

-- Backfill display IDs for existing rows (safe to re-run; WHERE guards skip already-set rows)
UPDATE core.hcps          SET hcp_id         = 'HCP-' || LPAD(nextval('core.hcp_id_seq')::text,          5, '0') WHERE hcp_id         IS NULL;
UPDATE core.receptionists SET receptionist_id = 'REC-' || LPAD(nextval('core.receptionist_id_seq')::text, 5, '0') WHERE receptionist_id IS NULL;
UPDATE core.labs           SET lab_id          = 'LAB-' || LPAD(nextval('core.lab_id_seq')::text,          5, '0') WHERE lab_id          IS NULL;
UPDATE core.admins         SET admin_id         = 'ADM-' || LPAD(nextval('core.admin_id_seq')::text,        5, '0') WHERE admin_id         IS NULL;
UPDATE core.patients       SET patient_auth_id  = 'PAT-' || LPAD(nextval('core.patient_auth_id_seq')::text, 5, '0') WHERE patient_auth_id  IS NULL;

-- Unique index: one active appointment per patient per doctor per day
CREATE UNIQUE INDEX IF NOT EXISTS uix_appt_patient_hcp_day
    ON core.appointments (patient_id, hcp_id, CAST(appointment_datetime AT TIME ZONE 'Asia/Kolkata' AS date))
    WHERE status != 'cancelled';

-- Full reset (DEV ONLY — destroys all data)
-- TRUNCATE core.patient_vitals, core.patient_documents, core.patient_consents,
--          core.hcp_availability, core.appointments RESTART IDENTITY CASCADE;
-- TRUNCATE core.patient_registrations RESTART IDENTITY CASCADE;
-- TRUNCATE core.hcps, core.receptionists, core.labs, core.admins, core.patients RESTART IDENTITY CASCADE;
-- ALTER SEQUENCE core.hcp_id_seq RESTART WITH 1;
-- ALTER SEQUENCE core.receptionist_id_seq RESTART WITH 1;
-- ALTER SEQUENCE core.lab_id_seq RESTART WITH 1;
-- ALTER SEQUENCE core.admin_id_seq RESTART WITH 1;
-- ALTER SEQUENCE core.patient_auth_id_seq RESTART WITH 1;
-- ALTER SEQUENCE core.patient_id_seq RESTART WITH 1;
-- ALTER SEQUENCE core.appointment_id_seq RESTART WITH 1;
-- =============================================================

-- =============================================================
-- HCP OPERATIONAL TABLES
-- =============================================================

CREATE SEQUENCE IF NOT EXISTS core.prescription_id_seq START 1 INCREMENT 1;

-- Prescriptions written by an HCP for a patient
CREATE TABLE IF NOT EXISTS core.prescriptions (
    id                BIGSERIAL    PRIMARY KEY,
    prescription_ref  VARCHAR(20)  UNIQUE NOT NULL,        -- RX-00001
    patient_id        BIGINT       NOT NULL REFERENCES core.patient_registrations (id),
    hcp_id            INTEGER      NOT NULL,               -- core.hcps.id
    clinic_code       VARCHAR(50)  NOT NULL,
    diagnosis         TEXT,
    drugs             JSONB        NOT NULL DEFAULT '[]',  -- [{name,dose,frequency,duration,notes}]
    instructions      TEXT,
    interaction_flags JSONB        DEFAULT '[]',           -- [{severity,description}]
    created_at        TIMESTAMPTZ  DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_rx_patient   ON core.prescriptions (patient_id);
CREATE INDEX IF NOT EXISTS idx_rx_hcp       ON core.prescriptions (hcp_id);
CREATE INDEX IF NOT EXISTS idx_rx_clinic_dt ON core.prescriptions (clinic_code, created_at);

-- Gene reports parsed from uploaded gene test files
CREATE TABLE IF NOT EXISTS core.gene_reports (
    id               BIGSERIAL   PRIMARY KEY,
    patient_id       BIGINT      NOT NULL REFERENCES core.patient_registrations (id),
    hcp_id           INTEGER,                              -- who ordered it (nullable for lab-uploaded)
    document_id      BIGINT      REFERENCES core.patient_documents (id),
    report_date      DATE,
    summary          TEXT,
    raw_json         JSONB,                                -- parsed gene data
    risk_level       VARCHAR(20) DEFAULT 'unknown',        -- low/medium/high/unknown
    ordered_by       INTEGER,                              -- core.hcps.id
    processed_at     TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_gene_patient ON core.gene_reports (patient_id);
CREATE INDEX IF NOT EXISTS idx_gene_hcp     ON core.gene_reports (hcp_id);

-- HCP-facing alerts (gene risk, drug interactions, missed follow-ups)
CREATE TABLE IF NOT EXISTS core.hcp_alerts (
    id           BIGSERIAL   PRIMARY KEY,
    hcp_id       INTEGER     NOT NULL,                     -- core.hcps.id
    patient_id   BIGINT      REFERENCES core.patient_registrations (id),
    alert_type   VARCHAR(50) NOT NULL,                     -- gene_risk / drug_interaction / missed_followup
    severity     VARCHAR(20) DEFAULT 'medium',             -- low / medium / high
    message      TEXT        NOT NULL,
    dismissed    BOOLEAN     DEFAULT FALSE,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_alerts_hcp ON core.hcp_alerts (hcp_id, dismissed);

-- INCREMENTAL MIGRATION for HCP tables
ALTER TABLE core.prescriptions  ADD COLUMN IF NOT EXISTS interaction_flags JSONB DEFAULT '[]';
-- (prescriptions, gene_reports, hcp_alerts were new in HCP branch — no prior columns to add)
