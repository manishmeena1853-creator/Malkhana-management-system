-- =====================================================================
-- MALKHANA SYSTEM: SAMPLE DATA + DEMO QUERIES
-- Run AFTER malkhana_schema.sql, on a fresh (just created) schema.
-- =====================================================================
SET search_path = malkhana, public;

-- ---------- 1. Master data ----------
INSERT INTO police_station (station_code, name, district, state) VALUES
 ('CP001','Connaught Place PS','New Delhi','Delhi'),
 ('HK002','Hauz Khas PS','South Delhi','Delhi');

INSERT INTO court (name, court_type, city) VALUES
 ('Patiala House Court','District & Sessions','New Delhi'),
 ('Saket Court','Metropolitan Magistrate','New Delhi');

INSERT INTO fsl_lab (name, city, specialisation) VALUES
 ('FSL Rohini Ballistics Unit','Delhi','Ballistics'),
 ('FSL Rohini Narcotics Unit','Delhi','Narcotics');

INSERT INTO officer (badge_no, full_name, rank, station_id) VALUES
 ('DP1001','Rajesh Kumar','Inspector',1),
 ('DP1002','Anita Sharma','Sub-Inspector',1),
 ('DP1003','Vikram Singh','Head Constable',1),
 ('DP2001','Suresh Yadav','Inspector',2);

INSERT INTO app_user (officer_id, username, password_hash, role) VALUES
 (1,'rajesh','demo_hash_1','SHO'),
 (2,'anita','demo_hash_2','INVESTIGATING_OFFICER'),
 (3,'vikram','demo_hash_3','MALKHANA_INCHARGE');

INSERT INTO malkhana (station_id, name, type, incharge_id) VALUES
 (1,'Main Malkhana','GENERAL',3),
 (1,'Arms Room','ARMS',3);

INSERT INTO storage_location (malkhana_id, rack, shelf, bin) VALUES
 (1,'A','1','1'),   -- location 1
 (1,'A','1','2'),   -- location 2
 (1,'B','2','1'),   -- location 3
 (2,'R1','S1','-'); -- location 4

-- ---------- 2. Cases and people ----------
INSERT INTO case_file (station_id, fir_no, fir_date, sections, io_id, court_id, court_case_no, status) VALUES
 (1,'45/2026','2026-03-10','BNS 303(2)',2,1,'CC-118/2026','TRIAL'),
 (1,'46/2026','2026-04-02','NDPS 21',2,1,NULL,'UNDER_INVESTIGATION'),
 (1,'51/2026','2026-05-15','Arms Act 25',1,2,NULL,'CHARGESHEETED');

INSERT INTO person (full_name, father_name, gender, address) VALUES
 ('Amit Verma','Ramesh Verma','M','Karol Bagh, Delhi'),
 ('Ravi Mehra','Suresh Mehra','M','Rajouri Garden, Delhi'),
 ('Sunil Das','Gopal Das','M','Lajpat Nagar, Delhi'),
 ('Pooja Nair','Mohan Nair','F','Saket, Delhi');

INSERT INTO case_person (case_id, person_id, role) VALUES
 (1,1,'ACCUSED'), (1,2,'COMPLAINANT'),
 (2,3,'ACCUSED'),
 (3,1,'ACCUSED'), (3,4,'WITNESS');

-- ---------- 3. Property (supertype) ----------
INSERT INTO property
 (case_id, malkhana_reg_no, seizure_memo_no, category, description,
  quantity, unit, seized_on, seized_from, seized_by, est_value) VALUES
 (1,'MR-2026-001','SM-01','ELECTRONIC','Samsung mobile phone, black',1,'pcs','2026-03-10 14:00+05:30','Karol Bagh',2,15000),
 (1,'MR-2026-002','SM-02','CASH_VALUABLES','Cash recovered from accused',1,'lot','2026-03-10 14:30+05:30','Karol Bagh',2,45000),
 (2,'MR-2026-003','SM-03','NARCOTICS','Brown powder packet (suspected heroin)',1,'pkt','2026-04-02 21:00+05:30','Lajpat Nagar',2,NULL),
 (3,'MR-2026-004','SM-04','ARMS','Country-made pistol',1,'pcs','2026-05-15 11:00+05:30','Karol Bagh',1,NULL),
 (1,'MR-2026-005','SM-05','VEHICLE','Black motorcycle used in offence',1,'pcs','2026-03-11 09:00+05:30','Karol Bagh',2,60000);

-- ---------- 4. Subtypes ----------
INSERT INTO electronic_property (property_id, device_type, make_model, imei_serial)
 VALUES (1,'Mobile phone','Samsung Galaxy A14','356938035643809');
INSERT INTO cash_valuables_property (property_id, item_kind, amount)
 VALUES (2,'CASH',45000);
INSERT INTO narcotics_property (property_id, substance, gross_wt_g, net_wt_g, quantity_class, sample_drawn)
 VALUES (3,'Heroin (suspected)',252.000,250.000,'COMMERCIAL',TRUE);
INSERT INTO arms_property (property_id, weapon_type, caliber, rounds_count)
 VALUES (4,'Country-made pistol','.315',2);
INSERT INTO vehicle_property (property_id, reg_no, chassis_no, make_model, colour)
 VALUES (5,'DL8SAB1234','MD2A11CY5KWE00001','Bajaj Pulsar 150','Black');

-- ---------- 5. Seal + court order + FSL request ----------
INSERT INTO property_seal (property_id, seal_no, sealed_by) VALUES
 (3,'SEAL-9001',2), (4,'SEAL-9002',1);

INSERT INTO court_order (case_id, court_id, order_no, order_date, type, details) VALUES
 (1,1,'ORD-77/2026','2026-08-20','RELEASE','Cash released on superdari to owner');
INSERT INTO court_order_property (order_id, property_id) VALUES (1,2);

INSERT INTO fsl_request (property_id, lab_id, sent_on, purpose) VALUES
 (3,2,'2026-04-05','Confirm substance and purity');

-- ---------- 6. Chain of custody (triggers update property status/location) ----------
-- Deposits
INSERT INTO custody_txn (property_id,type,txn_time,to_location_id,handed_by,received_by_officer,authorised_by,remarks) VALUES
 (1,'DEPOSIT','2026-03-10 18:00+05:30',1,2,3,1,'Deposited after seizure'),
 (2,'DEPOSIT','2026-03-10 18:10+05:30',2,2,3,1,'Cash counted in presence of witness'),
 (3,'DEPOSIT','2026-04-02 23:00+05:30',3,2,3,1,'Sealed packet deposited'),
 (4,'DEPOSIT','2026-05-15 15:00+05:30',4,1,3,1,'Weapon deposited in arms room'),
 (5,'DEPOSIT','2026-03-11 12:00+05:30',3,2,3,1,'Vehicle parked in yard rack');

-- Movements
INSERT INTO custody_txn (property_id,type,txn_time,from_location_id,handed_by,received_by_officer,authorised_by,fsl_req_id,remarks) VALUES
 (3,'ISSUE_TO_FSL','2026-04-05 10:00+05:30',3,3,2,1,1,'Sent to FSL for analysis');

INSERT INTO custody_txn (property_id,type,txn_time,from_location_id,handed_by,received_by_officer,authorised_by,remarks) VALUES
 (4,'ISSUE_TO_COURT','2026-06-10 09:30+05:30',4,3,2,1,'Produced in court on hearing date');
INSERT INTO custody_txn (property_id,type,txn_time,to_location_id,handed_by,received_by_officer,authorised_by,remarks) VALUES
 (4,'RETURN','2026-06-10 16:00+05:30',4,2,3,1,'Returned after hearing');

-- Phone sent to court >30 days ago and still outside (shows in overdue view)
INSERT INTO custody_txn (property_id,type,txn_time,from_location_id,handed_by,received_by_officer,authorised_by,remarks) VALUES
 (1,'ISSUE_TO_COURT', now() - interval '45 days',1,3,2,1,'Produced in court, not yet returned');

-- Cash released to owner on court order
INSERT INTO custody_txn (property_id,type,txn_time,from_location_id,handed_by,received_by_person,authorised_by,order_id,remarks) VALUES
 (2,'RELEASE_TO_OWNER','2026-08-21 12:00+05:30',2,3,2,1,1,'Released as per ORD-77/2026');

-- ---------- 7. Inspection ----------
INSERT INTO inspection (malkhana_id, inspected_by, inspected_on, remarks) VALUES
 (1,4,'2026-09-01','Monthly inspection by SHO of another station');
INSERT INTO inspection_item (inspection_id, property_id, found_ok, note) VALUES
 (1,3,TRUE,'Seal intact'),(1,5,TRUE,NULL);


-- =====================================================================
-- DEMO QUERIES (copy one at a time into the Query Tool)
-- =====================================================================

-- Q1: Everything currently stored in the malkhana, with location
SELECT * FROM v_malkhana_stock;

-- Q2: Full chain of custody of one item
SELECT * FROM v_chain_of_custody WHERE malkhana_reg_no = 'MR-2026-004';

-- Q3: Items outside the malkhana for more than 30 days
SELECT * FROM v_overdue_issues;

-- Q4: Count of property by category and status
SELECT category, status, COUNT(*) AS total
FROM property GROUP BY category, status ORDER BY category;

-- Q5: Property of each case with the investigating officer
SELECT c.fir_no, c.sections, o.full_name AS io, p.malkhana_reg_no, p.description, p.status
FROM case_file c
JOIN officer o  ON o.officer_id = c.io_id
JOIN property p ON p.case_id = c.case_id
ORDER BY c.fir_no;

-- Q6: Accused persons and the property seized in their cases
SELECT pe.full_name AS accused, c.fir_no, p.description
FROM person pe
JOIN case_person cp ON cp.person_id = pe.person_id AND cp.role = 'ACCUSED'
JOIN case_file c    ON c.case_id = cp.case_id
JOIN property p     ON p.case_id = c.case_id;

-- Q7: Narcotics details joined with the supertype (specialization in action)
SELECT p.malkhana_reg_no, p.description, n.substance, n.net_wt_g, n.quantity_class
FROM property p JOIN narcotics_property n USING (property_id);

-- Q8: How many custody actions each officer received
SELECT o.full_name, COUNT(*) AS items_received
FROM custody_txn t JOIN officer o ON o.officer_id = t.received_by_officer
GROUP BY o.full_name ORDER BY items_received DESC;

-- Q9: PROOF OF TRIGGERS (each should fail with an error message)
-- (a) Release without a court order:
--   INSERT INTO custody_txn (property_id,type,from_location_id,handed_by,authorised_by)
--   VALUES (5,'RELEASE_TO_OWNER',3,3,1);
-- (b) Edit the ledger:
--   UPDATE custody_txn SET remarks='tampered' WHERE txn_id = 1;
-- (c) Move an already released item:
--   INSERT INTO custody_txn (property_id,type,to_location_id,authorised_by)
--   VALUES (2,'DEPOSIT',2,1);
