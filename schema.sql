-- =====================================================================
-- MALKHANA MANAGEMENT SYSTEM  |  PostgreSQL schema (DBMS project)
-- Malkhana = police-station storeroom for seized / case property
-- =====================================================================

DROP SCHEMA IF EXISTS malkhana CASCADE;
CREATE SCHEMA malkhana;
SET search_path = malkhana, public;

-- ---------------------------------------------------------------------
-- 1. ENUM TYPES
-- ---------------------------------------------------------------------
CREATE TYPE user_role AS ENUM
  ('ADMIN','MALKHANA_INCHARGE','MALKHANA_CLERK','INVESTIGATING_OFFICER',
   'SHO','COURT_LIAISON','AUDITOR');
CREATE TYPE malkhana_type AS ENUM
  ('GENERAL','ARMS','NARCOTICS','VEHICLE','CASH_VALUABLES');
CREATE TYPE case_status AS ENUM
  ('UNDER_INVESTIGATION','CHARGESHEETED','TRIAL','DISPOSED','CLOSED');
CREATE TYPE person_role AS ENUM
  ('ACCUSED','COMPLAINANT','VICTIM','WITNESS','OWNER','CLAIMANT');
CREATE TYPE property_category AS ENUM
  ('ARMS','NARCOTICS','VEHICLE','CASH_VALUABLES','ELECTRONIC','OTHER');
CREATE TYPE property_status AS ENUM
  ('IN_MALKHANA','ISSUED_COURT','ISSUED_FSL','ISSUED_IO',
   'RELEASED','DISPOSED');
CREATE TYPE txn_type AS ENUM
  ('DEPOSIT','ISSUE_TO_COURT','ISSUE_TO_FSL','ISSUE_TO_IO','RETURN',
   'RELEASE_TO_OWNER','DISPOSAL','INTER_MALKHANA_TRANSFER');
CREATE TYPE order_type AS ENUM
  ('INTERIM_CUSTODY','RELEASE','DESTRUCTION','AUCTION','CONFISCATION');
CREATE TYPE disposal_method AS ENUM
  ('DESTROYED','AUCTIONED','CONFISCATED_TO_STATE','HANDED_TO_OWNER');

-- ---------------------------------------------------------------------
-- 2. ORGANISATION: station, court, FSL lab, officer, user
-- ---------------------------------------------------------------------
CREATE TABLE police_station (
  station_id   SERIAL PRIMARY KEY,
  station_code VARCHAR(15) NOT NULL UNIQUE,
  name         VARCHAR(100) NOT NULL,
  district     VARCHAR(60)  NOT NULL,
  state        VARCHAR(60)  NOT NULL,
  address      TEXT,
  phone        VARCHAR(15)
);

CREATE TABLE court (
  court_id   SERIAL PRIMARY KEY,
  name       VARCHAR(120) NOT NULL,
  court_type VARCHAR(40)  NOT NULL,         -- Sessions, JMFC, High Court...
  city       VARCHAR(60)  NOT NULL,
  UNIQUE (name, city)
);

CREATE TABLE fsl_lab (
  lab_id  SERIAL PRIMARY KEY,
  name    VARCHAR(120) NOT NULL,
  city    VARCHAR(60)  NOT NULL,
  specialisation VARCHAR(60),               -- ballistics, narcotics, cyber...
  UNIQUE (name, city)
);

CREATE TABLE officer (
  officer_id  SERIAL PRIMARY KEY,
  badge_no    VARCHAR(20) NOT NULL UNIQUE,
  full_name   VARCHAR(100) NOT NULL,
  rank        VARCHAR(40)  NOT NULL,        -- Constable, SI, Inspector...
  station_id  INT NOT NULL REFERENCES police_station(station_id),
  phone       VARCHAR(15),
  email       VARCHAR(120) UNIQUE,
  is_active   BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE app_user (
  user_id       SERIAL PRIMARY KEY,
  officer_id    INT NOT NULL UNIQUE REFERENCES officer(officer_id),
  username      VARCHAR(40) NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role          user_role NOT NULL,
  is_active     BOOLEAN NOT NULL DEFAULT TRUE,
  last_login    TIMESTAMPTZ
);

-- ---------------------------------------------------------------------
-- 3. STORAGE: malkhana -> storage_location
-- ---------------------------------------------------------------------
CREATE TABLE malkhana (
  malkhana_id  SERIAL PRIMARY KEY,
  station_id   INT NOT NULL REFERENCES police_station(station_id),
  name         VARCHAR(80) NOT NULL,
  type         malkhana_type NOT NULL DEFAULT 'GENERAL',
  incharge_id  INT REFERENCES officer(officer_id),
  UNIQUE (station_id, name)
);

CREATE TABLE storage_location (               -- weak entity of malkhana
  location_id  SERIAL PRIMARY KEY,
  malkhana_id  INT NOT NULL REFERENCES malkhana(malkhana_id) ON DELETE CASCADE,
  rack         VARCHAR(10) NOT NULL,
  shelf        VARCHAR(10) NOT NULL,
  bin          VARCHAR(10) NOT NULL DEFAULT '-',
  capacity     INT CHECK (capacity > 0),
  UNIQUE (malkhana_id, rack, shelf, bin)
);

-- ---------------------------------------------------------------------
-- 4. CASE and PERSON (with M:N role table)
-- ---------------------------------------------------------------------
CREATE TABLE case_file (
  case_id      SERIAL PRIMARY KEY,
  station_id   INT  NOT NULL REFERENCES police_station(station_id),
  fir_no       VARCHAR(20) NOT NULL,
  fir_date     DATE NOT NULL,
  sections     TEXT NOT NULL,               -- e.g. 'BNS 103, NDPS 20'
  io_id        INT NOT NULL REFERENCES officer(officer_id),
  court_id     INT REFERENCES court(court_id),
  court_case_no VARCHAR(40),
  status       case_status NOT NULL DEFAULT 'UNDER_INVESTIGATION',
  UNIQUE (station_id, fir_no, fir_date)
);

CREATE TABLE person (
  person_id    SERIAL PRIMARY KEY,
  full_name    VARCHAR(100) NOT NULL,
  father_name  VARCHAR(100),
  gender       CHAR(1) CHECK (gender IN ('M','F','O')),
  dob          DATE,
  address      TEXT,
  phone        VARCHAR(15),
  id_proof_type VARCHAR(30),
  id_proof_no   VARCHAR(40)
);

CREATE TABLE case_person (                    -- M:N  case <-> person
  case_id    INT NOT NULL REFERENCES case_file(case_id) ON DELETE CASCADE,
  person_id  INT NOT NULL REFERENCES person(person_id),
  role       person_role NOT NULL,
  PRIMARY KEY (case_id, person_id, role)
);

-- ---------------------------------------------------------------------
-- 5. PROPERTY (supertype) + disjoint SUBTYPES (EER specialisation)
-- ---------------------------------------------------------------------
CREATE TABLE property (
  property_id   BIGSERIAL PRIMARY KEY,
  case_id       INT NOT NULL REFERENCES case_file(case_id),
  malkhana_reg_no VARCHAR(25) NOT NULL UNIQUE,  -- register serial number
  seizure_memo_no VARCHAR(30) NOT NULL,
  category      property_category NOT NULL,
  description   TEXT NOT NULL,
  quantity      NUMERIC(12,3) NOT NULL CHECK (quantity > 0),
  unit          VARCHAR(15) NOT NULL DEFAULT 'pcs',
  seized_on     TIMESTAMPTZ NOT NULL,
  seized_from   TEXT,
  seized_by     INT NOT NULL REFERENCES officer(officer_id),
  seized_from_person INT REFERENCES person(person_id),
  est_value     NUMERIC(14,2) CHECK (est_value >= 0),
  status        property_status NOT NULL DEFAULT 'IN_MALKHANA',
  current_location_id INT REFERENCES storage_location(location_id),
  UNIQUE (property_id, category)               -- target for subtype FKs
);
CREATE INDEX idx_property_case   ON property(case_id);
CREATE INDEX idx_property_status ON property(status);

-- Subtypes: PK = FK, category pinned so one property has ONE subtype only
CREATE TABLE arms_property (
  property_id  BIGINT PRIMARY KEY,
  category     property_category NOT NULL DEFAULT 'ARMS' CHECK (category='ARMS'),
  weapon_type  VARCHAR(40) NOT NULL,
  make         VARCHAR(60),
  serial_no    VARCHAR(40),
  caliber      VARCHAR(20),
  rounds_count INT CHECK (rounds_count >= 0),
  licence_no   VARCHAR(40),
  FOREIGN KEY (property_id, category) REFERENCES property(property_id, category)
    ON DELETE CASCADE
);

CREATE TABLE narcotics_property (
  property_id  BIGINT PRIMARY KEY,
  category     property_category NOT NULL DEFAULT 'NARCOTICS' CHECK (category='NARCOTICS'),
  substance    VARCHAR(60) NOT NULL,
  gross_wt_g   NUMERIC(12,3) NOT NULL CHECK (gross_wt_g > 0),
  net_wt_g     NUMERIC(12,3) NOT NULL CHECK (net_wt_g > 0),
  quantity_class VARCHAR(12) CHECK (quantity_class IN ('SMALL','INTERMEDIATE','COMMERCIAL')),
  sample_drawn BOOLEAN NOT NULL DEFAULT FALSE,
  CHECK (net_wt_g <= gross_wt_g),
  FOREIGN KEY (property_id, category) REFERENCES property(property_id, category)
    ON DELETE CASCADE
);

CREATE TABLE vehicle_property (
  property_id  BIGINT PRIMARY KEY,
  category     property_category NOT NULL DEFAULT 'VEHICLE' CHECK (category='VEHICLE'),
  reg_no       VARCHAR(20),
  chassis_no   VARCHAR(30),
  engine_no    VARCHAR(30),
  make_model   VARCHAR(80),
  colour       VARCHAR(30),
  FOREIGN KEY (property_id, category) REFERENCES property(property_id, category)
    ON DELETE CASCADE
);

CREATE TABLE cash_valuables_property (
  property_id  BIGINT PRIMARY KEY,
  category     property_category NOT NULL DEFAULT 'CASH_VALUABLES' CHECK (category='CASH_VALUABLES'),
  item_kind    VARCHAR(20) NOT NULL CHECK (item_kind IN ('CASH','GOLD','SILVER','JEWELLERY','OTHER')),
  currency     CHAR(3) DEFAULT 'INR',
  amount       NUMERIC(14,2) CHECK (amount >= 0),
  weight_g     NUMERIC(10,3) CHECK (weight_g >= 0),
  purity       VARCHAR(10),
  FOREIGN KEY (property_id, category) REFERENCES property(property_id, category)
    ON DELETE CASCADE
);

CREATE TABLE electronic_property (
  property_id  BIGINT PRIMARY KEY,
  category     property_category NOT NULL DEFAULT 'ELECTRONIC' CHECK (category='ELECTRONIC'),
  device_type  VARCHAR(40) NOT NULL,
  make_model   VARCHAR(80),
  imei_serial  VARCHAR(40),
  FOREIGN KEY (property_id, category) REFERENCES property(property_id, category)
    ON DELETE CASCADE
);

-- Seals and photos attached to a property
CREATE TABLE property_seal (
  seal_id      SERIAL PRIMARY KEY,
  property_id  BIGINT NOT NULL REFERENCES property(property_id) ON DELETE CASCADE,
  seal_no      VARCHAR(30) NOT NULL,
  sealed_by    INT NOT NULL REFERENCES officer(officer_id),
  sealed_on    TIMESTAMPTZ NOT NULL DEFAULT now(),
  broken_on    TIMESTAMPTZ,
  broken_by    INT REFERENCES officer(officer_id),
  break_reason TEXT,
  CHECK (broken_on IS NULL OR broken_on >= sealed_on)
);

CREATE TABLE property_media (
  media_id     SERIAL PRIMARY KEY,
  property_id  BIGINT NOT NULL REFERENCES property(property_id) ON DELETE CASCADE,
  file_path    TEXT NOT NULL,
  media_type   VARCHAR(10) CHECK (media_type IN ('PHOTO','VIDEO','DOCUMENT')),
  uploaded_by  INT REFERENCES officer(officer_id),
  uploaded_on  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- 6. COURT ORDERS and CLAIMS
-- ---------------------------------------------------------------------
CREATE TABLE court_order (
  order_id     SERIAL PRIMARY KEY,
  case_id      INT NOT NULL REFERENCES case_file(case_id),
  court_id     INT NOT NULL REFERENCES court(court_id),
  order_no     VARCHAR(40) NOT NULL,
  order_date   DATE NOT NULL,
  type         order_type NOT NULL,
  details      TEXT,
  UNIQUE (court_id, order_no)
);

CREATE TABLE court_order_property (           -- M:N order <-> property
  order_id     INT    NOT NULL REFERENCES court_order(order_id) ON DELETE CASCADE,
  property_id  BIGINT NOT NULL REFERENCES property(property_id),
  PRIMARY KEY (order_id, property_id)
);

CREATE TABLE property_claim (
  claim_id     SERIAL PRIMARY KEY,
  property_id  BIGINT NOT NULL REFERENCES property(property_id),
  claimant_id  INT    NOT NULL REFERENCES person(person_id),
  claim_date   DATE   NOT NULL DEFAULT CURRENT_DATE,
  proof_details TEXT,
  status       VARCHAR(12) NOT NULL DEFAULT 'PENDING'
               CHECK (status IN ('PENDING','APPROVED','REJECTED'))
);

-- ---------------------------------------------------------------------
-- 7. CHAIN OF CUSTODY (append-only ledger)
-- ---------------------------------------------------------------------
CREATE TABLE fsl_request (
  fsl_req_id   SERIAL PRIMARY KEY,
  property_id  BIGINT NOT NULL REFERENCES property(property_id),
  lab_id       INT NOT NULL REFERENCES fsl_lab(lab_id),
  sent_on      DATE NOT NULL,
  purpose      TEXT NOT NULL,
  report_no    VARCHAR(40),
  report_received_on DATE,
  result_summary TEXT,
  CHECK (report_received_on IS NULL OR report_received_on >= sent_on)
);

CREATE TABLE custody_txn (
  txn_id        BIGSERIAL PRIMARY KEY,
  property_id   BIGINT NOT NULL REFERENCES property(property_id),
  type          txn_type NOT NULL,
  txn_time      TIMESTAMPTZ NOT NULL DEFAULT now(),
  from_location_id INT REFERENCES storage_location(location_id),
  to_location_id   INT REFERENCES storage_location(location_id),
  handed_by     INT REFERENCES officer(officer_id),
  received_by_officer INT REFERENCES officer(officer_id),
  received_by_person  INT REFERENCES person(person_id),   -- owner/court staff
  authorised_by INT NOT NULL REFERENCES officer(officer_id),
  order_id      INT REFERENCES court_order(order_id),
  fsl_req_id    INT REFERENCES fsl_request(fsl_req_id),
  remarks       TEXT,
  -- release / disposal are legal only with a court order
  CHECK (type NOT IN ('RELEASE_TO_OWNER','DISPOSAL') OR order_id IS NOT NULL),
  CHECK (type <> 'ISSUE_TO_FSL' OR fsl_req_id IS NOT NULL),
  CHECK (type <> 'DEPOSIT' OR to_location_id IS NOT NULL)
);
CREATE INDEX idx_txn_property ON custody_txn(property_id, txn_time);

CREATE TABLE disposal (
  disposal_id  SERIAL PRIMARY KEY,
  property_id  BIGINT NOT NULL UNIQUE REFERENCES property(property_id),
  order_id     INT NOT NULL REFERENCES court_order(order_id),
  method       disposal_method NOT NULL,
  disposed_on  DATE NOT NULL,
  disposed_by  INT NOT NULL REFERENCES officer(officer_id),
  witness_id   INT REFERENCES officer(officer_id),
  proceeds     NUMERIC(14,2) CHECK (proceeds >= 0),
  remarks      TEXT
);

-- ---------------------------------------------------------------------
-- 8. INSPECTION / AUDIT
-- ---------------------------------------------------------------------
CREATE TABLE inspection (
  inspection_id SERIAL PRIMARY KEY,
  malkhana_id   INT NOT NULL REFERENCES malkhana(malkhana_id),
  inspected_by  INT NOT NULL REFERENCES officer(officer_id),
  inspected_on  DATE NOT NULL DEFAULT CURRENT_DATE,
  remarks       TEXT
);

CREATE TABLE inspection_item (
  inspection_id INT    NOT NULL REFERENCES inspection(inspection_id) ON DELETE CASCADE,
  property_id   BIGINT NOT NULL REFERENCES property(property_id),
  found_ok      BOOLEAN NOT NULL,
  note          TEXT,
  PRIMARY KEY (inspection_id, property_id)
);

CREATE TABLE audit_log (
  log_id     BIGSERIAL PRIMARY KEY,
  user_id    INT REFERENCES app_user(user_id),
  table_name VARCHAR(60) NOT NULL,
  record_id  TEXT NOT NULL,
  action     VARCHAR(10) NOT NULL CHECK (action IN ('INSERT','UPDATE','DELETE')),
  old_data   JSONB,
  new_data   JSONB,
  logged_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- 9. TRIGGERS
-- ---------------------------------------------------------------------
-- 9a. Custody ledger is immutable
CREATE OR REPLACE FUNCTION fn_block_txn_change() RETURNS trigger AS $$
BEGIN
  -- the app may delete a mistaken property together with its history
  -- (it sets malkhana.allow_cleanup = 'on' and writes a copy to audit_log first)
  IF TG_OP = 'DELETE' AND current_setting('malkhana.allow_cleanup', true) = 'on' THEN
    RETURN OLD;
  END IF;
  RAISE EXCEPTION 'custody_txn is append-only; corrections need a new entry';
END; $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_txn_immutable
  BEFORE UPDATE OR DELETE ON custody_txn
  FOR EACH ROW EXECUTE FUNCTION fn_block_txn_change();

-- 9b. Validate transition + keep property status/location in sync
CREATE OR REPLACE FUNCTION fn_apply_custody_txn() RETURNS trigger AS $$
DECLARE
  cur property_status;
BEGIN
  SELECT status INTO cur FROM property WHERE property_id = NEW.property_id FOR UPDATE;

  IF cur IN ('RELEASED','DISPOSED') THEN
    RAISE EXCEPTION 'Property % is already % - no further movement allowed',
                    NEW.property_id, cur;
  END IF;

  IF NEW.type IN ('ISSUE_TO_COURT','ISSUE_TO_FSL','ISSUE_TO_IO',
                  'RELEASE_TO_OWNER','DISPOSAL','INTER_MALKHANA_TRANSFER')
     AND cur <> 'IN_MALKHANA' THEN
    RAISE EXCEPTION 'Property % must be IN_MALKHANA for %', NEW.property_id, NEW.type;
  END IF;

  IF NEW.type = 'RETURN' AND cur = 'IN_MALKHANA' THEN
    RAISE EXCEPTION 'Property % is already in malkhana', NEW.property_id;
  END IF;

  UPDATE property SET
    status = CASE NEW.type
      WHEN 'DEPOSIT'                 THEN 'IN_MALKHANA'::property_status
      WHEN 'RETURN'                  THEN 'IN_MALKHANA'
      WHEN 'INTER_MALKHANA_TRANSFER' THEN 'IN_MALKHANA'
      WHEN 'ISSUE_TO_COURT'          THEN 'ISSUED_COURT'
      WHEN 'ISSUE_TO_FSL'            THEN 'ISSUED_FSL'
      WHEN 'ISSUE_TO_IO'             THEN 'ISSUED_IO'
      WHEN 'RELEASE_TO_OWNER'        THEN 'RELEASED'
      WHEN 'DISPOSAL'                THEN 'DISPOSED'
    END,
    current_location_id = CASE
      WHEN NEW.type IN ('DEPOSIT','RETURN','INTER_MALKHANA_TRANSFER')
        THEN NEW.to_location_id
      ELSE NULL END
  WHERE property_id = NEW.property_id;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_txn_apply
  AFTER INSERT ON custody_txn   -- (BEFORE would also work; AFTER keeps ledger row visible)
  FOR EACH ROW EXECUTE FUNCTION fn_apply_custody_txn();

-- 9c. Generic audit trigger for key tables
CREATE OR REPLACE FUNCTION fn_audit() RETURNS trigger AS $$
DECLARE
  uid INT := NULLIF(current_setting('malkhana.user_id', true), '')::INT;
  rid TEXT;
BEGIN
  IF TG_OP = 'DELETE' THEN
    rid := to_jsonb(OLD) ->> TG_ARGV[0];
    INSERT INTO audit_log(user_id,table_name,record_id,action,old_data)
    VALUES (uid, TG_TABLE_NAME, rid, 'DELETE', to_jsonb(OLD));
    RETURN OLD;
  ELSE
    rid := to_jsonb(NEW) ->> TG_ARGV[0];
    INSERT INTO audit_log(user_id,table_name,record_id,action,old_data,new_data)
    VALUES (uid, TG_TABLE_NAME, rid, TG_OP,
            CASE WHEN TG_OP='UPDATE' THEN to_jsonb(OLD) END, to_jsonb(NEW));
    RETURN NEW;
  END IF;
END; $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_audit_property AFTER INSERT OR UPDATE OR DELETE ON property
  FOR EACH ROW EXECUTE FUNCTION fn_audit('property_id');
CREATE TRIGGER trg_audit_case AFTER INSERT OR UPDATE OR DELETE ON case_file
  FOR EACH ROW EXECUTE FUNCTION fn_audit('case_id');
CREATE TRIGGER trg_audit_order AFTER INSERT OR UPDATE OR DELETE ON court_order
  FOR EACH ROW EXECUTE FUNCTION fn_audit('order_id');

-- ---------------------------------------------------------------------
-- 10. USEFUL VIEWS
-- ---------------------------------------------------------------------
CREATE VIEW v_malkhana_stock AS
SELECT m.name AS malkhana, p.malkhana_reg_no, p.category, p.description,
       c.fir_no, ps.name AS station, sl.rack, sl.shelf, sl.bin
FROM property p
JOIN case_file c         ON c.case_id = p.case_id
JOIN police_station ps   ON ps.station_id = c.station_id
JOIN storage_location sl ON sl.location_id = p.current_location_id
JOIN malkhana m          ON m.malkhana_id = sl.malkhana_id
WHERE p.status = 'IN_MALKHANA';

CREATE VIEW v_chain_of_custody AS
SELECT t.property_id, p.malkhana_reg_no, t.txn_time, t.type,
       h.full_name AS handed_by, r.full_name AS received_by,
       a.full_name AS authorised_by, co.order_no
FROM custody_txn t
JOIN property p ON p.property_id = t.property_id
LEFT JOIN officer h ON h.officer_id = t.handed_by
LEFT JOIN officer r ON r.officer_id = t.received_by_officer
JOIN officer a      ON a.officer_id = t.authorised_by
LEFT JOIN court_order co ON co.order_id = t.order_id
ORDER BY t.property_id, t.txn_time;

-- Property out of malkhana for > 30 days (pending-return alert)
CREATE VIEW v_overdue_issues AS
SELECT p.property_id, p.malkhana_reg_no, p.status,
       max(t.txn_time) AS issued_on,
       now() - max(t.txn_time) AS outside_since
FROM property p
JOIN custody_txn t ON t.property_id = p.property_id
WHERE p.status IN ('ISSUED_COURT','ISSUED_FSL','ISSUED_IO')
GROUP BY p.property_id, p.malkhana_reg_no, p.status
HAVING now() - max(t.txn_time) > interval '30 days';
