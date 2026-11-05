"""
MALKHANA MANAGEMENT SYSTEM - Flask backend
Run:  python app.py     then open  http://127.0.0.1:5000
"""
import hmac
import os
import getpass
import secrets
import time
from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import check_password_hash, generate_password_hash
from flask import Flask, render_template, request, redirect, url_for, flash, abort, session, has_request_context

# ---------------------------------------------------------------------
# 1. DATABASE SETTINGS  (change the password to YOUR postgres password)
# ---------------------------------------------------------------------
DB = dict(
    host=os.getenv("DB_HOST", "localhost"),
    port=os.getenv("DB_PORT", "5432"),
    dbname=os.getenv("DB_NAME", "malkhana_db"),
    user=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASSWORD", "manishpgsql"),
)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)   # never hard-code a real secret
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")


# ---------------------------------------------------------------------
# 2. SMALL HELPERS
# ---------------------------------------------------------------------
def conn():
    c = psycopg2.connect(**DB, options="-c search_path=malkhana,public")
    if has_request_context() and session.get("uid"):
        with c.cursor() as cur:      # the audit trigger reads this to record WHO made a change
            cur.execute("SELECT set_config('malkhana.user_id', %s, false)", (str(session["uid"]),))
        c.commit()
    return c


def run(sql, params=None):
    """Run one query and return rows as dictionaries."""
    c = conn()
    try:
        with c.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params or ())
            rows = cur.fetchall() if cur.description else []
        c.commit()
        return rows
    finally:
        c.close()


def tx(work):
    """Run several statements as ONE transaction (all succeed or none)."""
    c = conn()
    try:
        with c.cursor(cursor_factory=RealDictCursor) as cur:
            result = work(cur)
        c.commit()
        return result
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def val(name):
    v = request.form.get(name, "").strip()
    return v or None


def ival(name):
    v = val(name)
    return int(v) if v else None


def friendly(e):
    msg = getattr(getattr(e, "diag", None), "message_primary", None) or str(e)
    if "custody_txn_check" in msg:
        return ("Rule violated: Release/Disposal needs a court order, "
                "Issue-to-FSL needs an FSL request, Deposit needs a storage location.")
    if "violates foreign key constraint" in msg:
        return ("Cannot delete: other records still depend on this one "
                "(for example property, court orders or custody history). Remove those first.")
    if "duplicate key" in msg:
        return "This record already exists (duplicate value)."
    return msg


def officers():
    return run("SELECT officer_id AS v, full_name||' ('||rank||')' AS l "
               "FROM officer WHERE is_active ORDER BY full_name")


def locations():
    return run("SELECT sl.location_id AS v, m.name||' / '||sl.rack||'-'||sl.shelf||'-'||sl.bin AS l "
               "FROM storage_location sl JOIN malkhana m ON m.malkhana_id=sl.malkhana_id ORDER BY 2")


CATEGORIES = ["ARMS", "NARCOTICS", "VEHICLE", "CASH_VALUABLES", "ELECTRONIC", "OTHER"]
SUBTYPE_TABLE = {
    "ARMS": "arms_property", "NARCOTICS": "narcotics_property",
    "VEHICLE": "vehicle_property", "CASH_VALUABLES": "cash_valuables_property",
    "ELECTRONIC": "electronic_property",
}
CASE_STATUS = ["UNDER_INVESTIGATION", "CHARGESHEETED", "TRIAL", "DISPOSED", "CLOSED"]



# ---------------------------------------------------------------------
# SECURITY: login, roles, CSRF protection
# ---------------------------------------------------------------------
STAFF = {"ADMIN", "SHO", "MALKHANA_INCHARGE", "MALKHANA_CLERK"}
ROLES = ["ADMIN", "SHO", "MALKHANA_INCHARGE", "MALKHANA_CLERK",
         "INVESTIGATING_OFFICER", "COURT_LIAISON", "AUDITOR"]
# endpoint -> (allowed roles, True if only POST (changes) is restricted and viewing is open)
RULES = {
    "property_new": (STAFF, False),
    "property_move": (STAFF, True),
    "cases": ({"ADMIN", "SHO", "INVESTIGATING_OFFICER"}, True),
    "orders": ({"ADMIN", "SHO", "COURT_LIAISON"}, True),
    "master": ({"ADMIN"}, True),
    "master_delete": ({"ADMIN"}, True),
    "case_delete": ({"ADMIN"}, True),
    "order_delete": ({"ADMIN"}, True),
    "property_delete": ({"ADMIN"}, True),
    "audit": ({"ADMIN", "SHO", "AUDITOR"}, False),
    "users": ({"ADMIN"}, False),
}
FAILS = {}   # username -> (wrong attempts, window start)


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


@app.context_processor
def inject_user():
    return dict(csrf_token=csrf_token, role=session.get("role"),
                user_name=session.get("name"), staff_roles=STAFF)


@app.before_request
def guard():
    ep = request.endpoint
    if ep is None or ep == "static":
        return
    if request.method == "POST":      # block forged requests from other websites
        sent = request.form.get("csrf_token", "").encode()
        if not sent or not hmac.compare_digest(sent, session.get("csrf", "").encode()):
            abort(400, "Security token missing or expired. Go back, refresh the page and try again.")
    if ep == "login":
        return
    if not session.get("uid"):
        return redirect(url_for("login"))
    rule = RULES.get(ep)
    if rule and (not rule[1] or request.method == "POST"):
        if session.get("role") not in rule[0]:
            flash("You do not have permission for this action (your role: %s)." % session.get("role"), "danger")
            return redirect(url_for("dashboard"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        uname = (val("username") or "").lower()
        pw = request.form.get("password", "")
        cnt, since = FAILS.get(uname, (0, time.time()))
        if time.time() - since > 60:
            cnt, since = 0, time.time()
        if cnt >= 5:
            flash("Too many wrong attempts. Wait one minute and try again.", "danger")
            return render_template("login.html")
        rows = run("""SELECT u.user_id, u.password_hash, u.role, o.full_name
                      FROM app_user u JOIN officer o ON o.officer_id=u.officer_id
                      WHERE lower(u.username)=%s AND u.is_active""", (uname,))
        if rows and check_password_hash(rows[0]["password_hash"], pw):
            FAILS.pop(uname, None)
            session.clear()                      # fresh session after login
            session.update(uid=rows[0]["user_id"], name=rows[0]["full_name"], role=rows[0]["role"])
            session["csrf"] = secrets.token_hex(16)
            run("UPDATE app_user SET last_login = now() WHERE user_id=%s", (rows[0]["user_id"],))
            return redirect(url_for("dashboard"))
        FAILS[uname] = (cnt + 1, since)
        flash("Wrong username or password.", "danger")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/password", methods=["GET", "POST"])
def change_password():
    if request.method == "POST":
        old, new, new2 = (request.form.get(k, "") for k in ("old", "new", "new2"))
        row = run("SELECT password_hash FROM app_user WHERE user_id=%s", (session["uid"],))
        if not row or not check_password_hash(row[0]["password_hash"], old):
            flash("Current password is wrong.", "danger")
        elif len(new) < 8:
            flash("New password must be at least 8 characters.", "danger")
        elif new != new2:
            flash("New passwords do not match.", "danger")
        else:
            run("UPDATE app_user SET password_hash=%s WHERE user_id=%s",
                (generate_password_hash(new, method="pbkdf2:sha256"), session["uid"]))
            flash("Password changed.", "success")
            return redirect(url_for("dashboard"))
    return render_template("password.html")


@app.route("/users", methods=["GET", "POST"])
def users():
    if request.method == "POST":
        try:
            pw = request.form.get("password", "")
            if len(pw) < 8:
                raise ValueError("Password must be at least 8 characters.")
            run("INSERT INTO app_user (officer_id, username, password_hash, role) VALUES (%s,%s,%s,%s)",
                (ival("officer_id"), (val("username") or "").lower(),
                 generate_password_hash(pw, method="pbkdf2:sha256"), val("role")))
            flash("User created.", "success")
        except Exception as e:
            flash(friendly(e), "danger")
        return redirect(url_for("users"))
    rows = run("""SELECT u.user_id AS "ID", u.username AS "Username", o.full_name AS "Officer",
                  u.role AS "Role", u.is_active AS "Active",
                  to_char(u.last_login,'DD-Mon-YYYY HH24:MI') AS "Last login"
                  FROM app_user u JOIN officer o ON o.officer_id=u.officer_id ORDER BY u.user_id""")
    free = run("""SELECT officer_id AS v, full_name||' ('||rank||')' AS l FROM officer
                  WHERE is_active AND officer_id NOT IN (SELECT officer_id FROM app_user) ORDER BY full_name""")
    return render_template("users.html", rows=rows, officers=free, roles=ROLES)


DEMO_USERS = {"rajesh": "Sho@12345", "anita": "Io@12345", "vikram": "Store@12345"}


def seed_demo_users():
    """Gives the demo accounts REAL (hashed) passwords the first time the app starts."""
    try:
        for r in run("SELECT username, password_hash FROM app_user"):
            if r["username"] in DEMO_USERS and not r["password_hash"].startswith("pbkdf2:"):
                run("UPDATE app_user SET password_hash=%s WHERE username=%s",
                    (generate_password_hash(DEMO_USERS[r["username"]], method="pbkdf2:sha256"), r["username"]))
        if not run("SELECT 1 FROM app_user WHERE username='admin'"):
            free = run("SELECT officer_id FROM officer WHERE officer_id NOT IN "
                       "(SELECT officer_id FROM app_user) ORDER BY officer_id LIMIT 1")
            if free:
                run("INSERT INTO app_user (officer_id, username, password_hash, role) VALUES (%s,'admin',%s,'ADMIN')",
                    (free[0]["officer_id"], generate_password_hash("Admin@123", method="pbkdf2:sha256")))
            else:
                print("Note: no officer without an account is left to attach the admin user to.")
    except Exception as e:
        print("Note: could not prepare demo users:", e)

# ---------------------------------------------------------------------
# 3. DASHBOARD
# ---------------------------------------------------------------------
@app.route("/")
def dashboard():
    stats = run("""SELECT
        (SELECT COUNT(*) FROM property) AS total,
        (SELECT COUNT(*) FROM property WHERE status='IN_MALKHANA') AS in_store,
        (SELECT COUNT(*) FROM property WHERE status IN ('ISSUED_COURT','ISSUED_FSL','ISSUED_IO')) AS outside,
        (SELECT COUNT(*) FROM case_file) AS cases""")[0]
    by_status = run('SELECT status AS "Status", COUNT(*) AS "Items" FROM property GROUP BY status ORDER BY 2 DESC')
    by_cat = run('SELECT category AS "Category", COUNT(*) AS "Items" FROM property GROUP BY category ORDER BY 2 DESC')
    stock = run("SELECT * FROM v_malkhana_stock")
    overdue = run("SELECT * FROM v_overdue_issues")
    recent = run("""SELECT to_char(t.txn_time,'DD-Mon-YYYY HH24:MI') AS "When",
                    p.malkhana_reg_no AS "Reg No", t.type AS "Action", a.full_name AS "Authorised by"
                    FROM custody_txn t JOIN property p ON p.property_id=t.property_id
                    JOIN officer a ON a.officer_id=t.authorised_by
                    ORDER BY t.txn_time DESC, t.txn_id DESC LIMIT 8""")
    return render_template("dashboard.html", stats=stats, by_status=by_status,
                           by_cat=by_cat, stock=stock, overdue=overdue, recent=recent)


# ---------------------------------------------------------------------
# 4. MASTER DATA (stations, officers, courts, labs, malkhana, locations, persons)
#    field = (column, label, kind, options, required)
# ---------------------------------------------------------------------
Q_STATION = "SELECT station_id, name FROM police_station ORDER BY name"
Q_MALKHANA = "SELECT malkhana_id, name FROM malkhana ORDER BY name"
Q_OFFICER = "SELECT officer_id, full_name FROM officer ORDER BY full_name"

MASTERS = {
    "stations": dict(title="Police Stations", table="police_station", pk="station_id", fields=[
        ("station_code", "Station code", "text", None, True),
        ("name", "Name", "text", None, True),
        ("district", "District", "text", None, True),
        ("state", "State", "text", None, True)],
        list_sql="SELECT station_id, station_code, name, district, state FROM police_station ORDER BY 1 DESC"),
    "officers": dict(title="Officers", table="officer", pk="officer_id", fields=[
        ("badge_no", "Badge no", "text", None, True),
        ("full_name", "Full name", "text", None, True),
        ("rank", "Rank", "text", None, True),
        ("station_id", "Station", "select", Q_STATION, True)],
        list_sql="""SELECT o.officer_id, o.badge_no, o.full_name, o.rank, ps.name AS station
                    FROM officer o JOIN police_station ps ON ps.station_id=o.station_id ORDER BY 1 DESC"""),
    "courts": dict(title="Courts", table="court", pk="court_id", fields=[
        ("name", "Court name", "text", None, True),
        ("court_type", "Court type", "text", None, True),
        ("city", "City", "text", None, True)],
        list_sql="SELECT * FROM court ORDER BY 1 DESC"),
    "labs": dict(title="FSL Labs", table="fsl_lab", pk="lab_id", fields=[
        ("name", "Lab name", "text", None, True),
        ("city", "City", "text", None, True),
        ("specialisation", "Specialisation", "text", None, False)],
        list_sql="SELECT * FROM fsl_lab ORDER BY 1 DESC"),
    "malkhanas": dict(title="Malkhanas (storerooms)", table="malkhana", pk="malkhana_id", fields=[
        ("station_id", "Station", "select", Q_STATION, True),
        ("name", "Malkhana name", "text", None, True),
        ("type", "Type", "select", ["GENERAL", "ARMS", "NARCOTICS", "VEHICLE", "CASH_VALUABLES"], True),
        ("incharge_id", "In-charge officer", "select", Q_OFFICER, False)],
        list_sql="""SELECT m.malkhana_id, ps.name AS station, m.name, m.type, o.full_name AS incharge
                    FROM malkhana m JOIN police_station ps ON ps.station_id=m.station_id
                    LEFT JOIN officer o ON o.officer_id=m.incharge_id ORDER BY 1 DESC"""),
    "locations": dict(title="Storage Locations (rack/shelf/bin)", table="storage_location", pk="location_id", fields=[
        ("malkhana_id", "Malkhana", "select", Q_MALKHANA, True),
        ("rack", "Rack", "text", None, True),
        ("shelf", "Shelf", "text", None, True),
        ("bin", "Bin", "text", None, True)],
        list_sql="""SELECT l.location_id, m.name AS malkhana, l.rack, l.shelf, l.bin
                    FROM storage_location l JOIN malkhana m ON m.malkhana_id=l.malkhana_id ORDER BY 1 DESC"""),
    "persons": dict(title="Persons (accused / complainant / witness)", table="person", pk="person_id", fields=[
        ("full_name", "Full name", "text", None, True),
        ("father_name", "Father's name", "text", None, False),
        ("gender", "Gender", "select", ["M", "F", "O"], False),
        ("address", "Address", "text", None, False),
        ("phone", "Phone", "text", None, False)],
        list_sql="SELECT person_id, full_name, father_name, gender, address, phone FROM person ORDER BY 1 DESC"),
}


def resolve_options(opts):
    if opts is None:
        return []
    if isinstance(opts, list):
        return [(o, o) for o in opts]
    return [tuple(r.values())[:2] for r in run(opts)]


@app.route("/master/<key>", methods=["GET", "POST"])
def master(key):
    m = MASTERS.get(key)
    if not m:
        abort(404)
    cols = [f[0] for f in m["fields"]]
    if request.method == "POST":
        try:
            run(f"INSERT INTO {m['table']} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})",
                [val(c) for c in cols])
            flash(f"Saved to {m['title']}.", "success")
        except Exception as e:
            flash(friendly(e), "danger")
        return redirect(url_for("master", key=key))
    fields = [dict(col=f[0], label=f[1], kind=f[2], options=resolve_options(f[3]), req=f[4])
              for f in m["fields"]]
    return render_template("master.html", m=m, key=key, fields=fields, rows=run(m["list_sql"]))


# ---------------------------------------------------------------------
# 5. CASES
# ---------------------------------------------------------------------
@app.route("/cases", methods=["GET", "POST"])
def cases():
    if request.method == "POST":
        def work(cur):
            cur.execute("""INSERT INTO case_file (station_id, fir_no, fir_date, sections, io_id,
                           court_id, court_case_no, status)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING case_id""",
                        (ival("station_id"), val("fir_no"), val("fir_date"), val("sections"),
                         ival("io_id"), ival("court_id"), val("court_case_no"), val("status")))
            cid = cur.fetchone()["case_id"]
            for field, role in (("accused", "ACCUSED"), ("complainant", "COMPLAINANT")):
                name = val(field)
                if name:
                    cur.execute("INSERT INTO person (full_name) VALUES (%s) RETURNING person_id", (name,))
                    pid = cur.fetchone()["person_id"]
                    cur.execute("INSERT INTO case_person (case_id, person_id, role) VALUES (%s,%s,%s)",
                                (cid, pid, role))
        try:
            tx(work)
            flash("Case registered.", "success")
        except Exception as e:
            flash(friendly(e), "danger")
        return redirect(url_for("cases"))
    rows = run("""SELECT c.case_id AS "ID", ps.name AS "Station", c.fir_no AS "FIR No",
                  c.fir_date AS "FIR Date", c.sections AS "Sections", o.full_name AS "IO",
                  c.status AS "Status",
                  (SELECT COUNT(*) FROM property p WHERE p.case_id=c.case_id) AS "Items"
                  FROM case_file c JOIN police_station ps ON ps.station_id=c.station_id
                  JOIN officer o ON o.officer_id=c.io_id ORDER BY c.case_id DESC""")
    return render_template("cases.html", rows=rows,
                           stations=resolve_options(Q_STATION), officers=officers(),
                           courts=resolve_options("SELECT court_id, name FROM court ORDER BY name"),
                           statuses=CASE_STATUS)


# ---------------------------------------------------------------------
# 6. PROPERTY: list/search, add, detail, movement
# ---------------------------------------------------------------------
@app.route("/property")
def property_list():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    where, params = [], []
    if q:
        where.append("""(p.malkhana_reg_no ILIKE %s OR p.description ILIKE %s OR c.fir_no ILIKE %s
                        OR p.seizure_memo_no ILIKE %s OR EXISTS (SELECT 1 FROM case_person cp
                        JOIN person pe ON pe.person_id=cp.person_id
                        WHERE cp.case_id=p.case_id AND pe.full_name ILIKE %s))""")
        params += [f"%{q}%"] * 5
    if status:
        where.append("p.status = %s")
        params.append(status)
    sql = """SELECT p.property_id, p.malkhana_reg_no, p.category, p.description, c.fir_no, p.status,
             COALESCE(m.name||' / '||sl.rack||'-'||sl.shelf||'-'||sl.bin, '-') AS location
             FROM property p JOIN case_file c ON c.case_id=p.case_id
             LEFT JOIN storage_location sl ON sl.location_id=p.current_location_id
             LEFT JOIN malkhana m ON m.malkhana_id=sl.malkhana_id"""
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY p.property_id DESC"
    return render_template("property_list.html", rows=run(sql, params), q=q, status=status)


@app.route("/property/new", methods=["GET", "POST"])
def property_new():
    if request.method == "POST":
        cat = val("category")

        def work(cur):
            cur.execute("SELECT COALESCE(MAX(property_id),0)+1 AS n FROM property")
            reg = f"MR-{datetime.now().year}-{cur.fetchone()['n']:03d}"
            cur.execute("""INSERT INTO property (case_id, malkhana_reg_no, seizure_memo_no, category,
                           description, quantity, unit, seized_on, seized_from, seized_by, est_value)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING property_id""",
                        (ival("case_id"), reg, val("seizure_memo_no"), cat, val("description"),
                         val("quantity") or 1, val("unit") or "pcs", val("seized_on"),
                         val("seized_from"), ival("seized_by"), val("est_value")))
            pid = cur.fetchone()["property_id"]
            if cat == "ARMS":
                cur.execute("""INSERT INTO arms_property (property_id, weapon_type, serial_no, caliber, rounds_count)
                               VALUES (%s,%s,%s,%s,%s)""",
                            (pid, val("a_weapon_type"), val("a_serial_no"), val("a_caliber"), val("a_rounds")))
            elif cat == "NARCOTICS":
                cur.execute("""INSERT INTO narcotics_property (property_id, substance, gross_wt_g, net_wt_g,
                               quantity_class, sample_drawn) VALUES (%s,%s,%s,%s,%s,%s)""",
                            (pid, val("n_substance"), val("n_gross"), val("n_net"),
                             val("n_class"), request.form.get("n_sample") == "on"))
            elif cat == "VEHICLE":
                cur.execute("""INSERT INTO vehicle_property (property_id, reg_no, chassis_no, make_model, colour)
                               VALUES (%s,%s,%s,%s,%s)""",
                            (pid, val("v_reg_no"), val("v_chassis"), val("v_model"), val("v_colour")))
            elif cat == "CASH_VALUABLES":
                cur.execute("""INSERT INTO cash_valuables_property (property_id, item_kind, amount, weight_g)
                               VALUES (%s,%s,%s,%s)""",
                            (pid, val("c_kind"), val("c_amount"), val("c_weight")))
            elif cat == "ELECTRONIC":
                cur.execute("""INSERT INTO electronic_property (property_id, device_type, make_model, imei_serial)
                               VALUES (%s,%s,%s,%s)""",
                            (pid, val("e_type"), val("e_model"), val("e_imei")))
            # first custody entry: DEPOSIT into the malkhana
            cur.execute("""INSERT INTO custody_txn (property_id, type, to_location_id, handed_by,
                           received_by_officer, authorised_by, remarks)
                           VALUES (%s,'DEPOSIT',%s,%s,%s,%s,'Deposited at registration')""",
                        (pid, ival("location_id"), ival("seized_by"), ival("received_by"), ival("authorised_by")))
            return pid, reg

        try:
            pid, reg = tx(work)
            flash(f"Property registered and deposited. Register No: {reg}", "success")
            return redirect(url_for("property_detail", pid=pid))
        except Exception as e:
            flash(friendly(e), "danger")
            return redirect(url_for("property_new"))
    cases_ = run("""SELECT c.case_id AS v, 'FIR '||c.fir_no||' - '||ps.name AS l
                    FROM case_file c JOIN police_station ps ON ps.station_id=c.station_id
                    ORDER BY c.case_id DESC""")
    return render_template("property_new.html", cases=cases_, officers=officers(),
                           locations=locations(), categories=CATEGORIES,
                           now=datetime.now().strftime("%Y-%m-%dT%H:%M"))


@app.route("/property/<int:pid>")
def property_detail(pid):
    found = run("""SELECT p.*, c.fir_no, c.sections, ps.name AS station,
                   COALESCE(m.name||' / '||sl.rack||'-'||sl.shelf||'-'||sl.bin, '-') AS location,
                   o.full_name AS seized_by_name
                   FROM property p JOIN case_file c ON c.case_id=p.case_id
                   JOIN police_station ps ON ps.station_id=c.station_id
                   JOIN officer o ON o.officer_id=p.seized_by
                   LEFT JOIN storage_location sl ON sl.location_id=p.current_location_id
                   LEFT JOIN malkhana m ON m.malkhana_id=sl.malkhana_id
                   WHERE p.property_id=%s""", (pid,))
    if not found:
        abort(404)
    p = found[0]
    sub = {}
    tbl = SUBTYPE_TABLE.get(p["category"])
    if tbl:
        r = run(f"SELECT * FROM {tbl} WHERE property_id=%s", (pid,))
        if r:
            sub = {k: v for k, v in r[0].items() if k not in ("property_id", "category")}
    history = run("""SELECT to_char(t.txn_time,'DD-Mon-YYYY HH24:MI') AS "When", t.type AS "Action",
                     h.full_name AS "Handed by", r.full_name AS "Received by",
                     a.full_name AS "Authorised by", co.order_no AS "Court order", t.remarks AS "Remarks"
                     FROM custody_txn t
                     LEFT JOIN officer h ON h.officer_id=t.handed_by
                     LEFT JOIN officer r ON r.officer_id=t.received_by_officer
                     JOIN officer a ON a.officer_id=t.authorised_by
                     LEFT JOIN court_order co ON co.order_id=t.order_id
                     WHERE t.property_id=%s ORDER BY t.txn_time, t.txn_id""", (pid,))
    orders = run("""SELECT co.order_id AS v, co.order_no||' ('||co.type||')' AS l
                    FROM court_order co JOIN court_order_property cop ON cop.order_id=co.order_id
                    WHERE cop.property_id=%s""", (pid,))
    labs = run("SELECT lab_id AS v, name AS l FROM fsl_lab ORDER BY name")
    if p["status"] == "IN_MALKHANA":
        actions = ["ISSUE_TO_COURT", "ISSUE_TO_FSL", "ISSUE_TO_IO", "RELEASE_TO_OWNER",
                   "DISPOSAL", "INTER_MALKHANA_TRANSFER"]
    elif p["status"] in ("ISSUED_COURT", "ISSUED_FSL", "ISSUED_IO"):
        actions = ["RETURN"]
    else:
        actions = []
    return render_template("property_detail.html", p=p, sub=sub, history=history, orders=orders,
                           labs=labs, actions=actions, officers=officers(), locations=locations())


@app.route("/property/<int:pid>/move", methods=["POST"])
def property_move(pid):
    t = val("type")

    def work(cur):
        cur.execute("SELECT current_location_id FROM property WHERE property_id=%s", (pid,))
        row = cur.fetchone()
        if not row:
            raise ValueError("Property not found")
        from_loc, to_loc = row["current_location_id"], ival("to_location")
        if t in ("RETURN", "INTER_MALKHANA_TRANSFER") and not to_loc:
            raise ValueError("Choose a storage location for this movement.")
        fsl_id = None
        if t == "ISSUE_TO_FSL":
            if not ival("lab_id"):
                raise ValueError("Choose an FSL lab.")
            cur.execute("""INSERT INTO fsl_request (property_id, lab_id, sent_on, purpose)
                           VALUES (%s,%s,CURRENT_DATE,%s) RETURNING fsl_req_id""",
                        (pid, ival("lab_id"), val("purpose") or "Examination"))
            fsl_id = cur.fetchone()["fsl_req_id"]
        if t == "DISPOSAL" and not val("method"):
            raise ValueError("Choose a disposal method.")
        cur.execute("""INSERT INTO custody_txn (property_id, type, from_location_id, to_location_id,
                       handed_by, received_by_officer, authorised_by, order_id, fsl_req_id, remarks)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (pid, t, from_loc, to_loc, ival("handed_by"), ival("received_by"),
                     ival("authorised_by"), ival("order_id"), fsl_id, val("remarks")))
        if t == "DISPOSAL":
            cur.execute("""INSERT INTO disposal (property_id, order_id, method, disposed_on, disposed_by)
                           VALUES (%s,%s,%s,CURRENT_DATE,%s)""",
                        (pid, ival("order_id"), val("method"), ival("handed_by")))

    try:
        tx(work)
        flash(f"Done: {t}", "success")
    except Exception as e:
        flash(friendly(e), "danger")
    return redirect(url_for("property_detail", pid=pid))


# ---------------------------------------------------------------------
# 7. COURT ORDERS
# ---------------------------------------------------------------------
@app.route("/orders", methods=["GET", "POST"])
def orders():
    if request.method == "POST":
        pids = [int(x) for x in request.form.getlist("property_ids")]

        def work(cur):
            if not pids:
                raise ValueError("Select at least one property.")
            cur.execute("SELECT DISTINCT case_id FROM property WHERE property_id = ANY(%s)", (pids,))
            case_ids = [r["case_id"] for r in cur.fetchall()]
            if len(case_ids) != 1:
                raise ValueError("All selected property must belong to the same case.")
            cur.execute("""INSERT INTO court_order (case_id, court_id, order_no, order_date, type, details)
                           VALUES (%s,%s,%s,%s,%s,%s) RETURNING order_id""",
                        (case_ids[0], ival("court_id"), val("order_no"), val("order_date"),
                         val("type"), val("details")))
            oid = cur.fetchone()["order_id"]
            for pid in pids:
                cur.execute("INSERT INTO court_order_property (order_id, property_id) VALUES (%s,%s)",
                            (oid, pid))
        try:
            tx(work)
            flash("Court order saved.", "success")
        except Exception as e:
            flash(friendly(e), "danger")
        return redirect(url_for("orders"))
    rows = run("""SELECT co.order_id AS "ID", c.name AS "Court", co.order_no AS "Order No",
                  co.order_date AS "Date", co.type AS "Type", cf.fir_no AS "FIR",
                  string_agg(p.malkhana_reg_no, ', ') AS "Property"
                  FROM court_order co JOIN court c ON c.court_id=co.court_id
                  JOIN case_file cf ON cf.case_id=co.case_id
                  LEFT JOIN court_order_property cop ON cop.order_id=co.order_id
                  LEFT JOIN property p ON p.property_id=cop.property_id
                  GROUP BY co.order_id, c.name, cf.fir_no ORDER BY co.order_id DESC""")
    props = run("""SELECT p.property_id AS v,
                   p.malkhana_reg_no||' - '||p.description||' (FIR '||c.fir_no||')' AS l
                   FROM property p JOIN case_file c ON c.case_id=p.case_id ORDER BY p.property_id DESC""")
    return render_template("orders.html", rows=rows, props=props,
                           courts=resolve_options("SELECT court_id, name FROM court ORDER BY name"),
                           types=["INTERIM_CUSTODY", "RELEASE", "DESTRUCTION", "AUCTION", "CONFISCATION"])



# ---------------------------------------------------------------------
# DELETE (blocked by the database if other records depend on the row)
# ---------------------------------------------------------------------
@app.route("/master/<key>/delete/<int:rid>", methods=["POST"])
def master_delete(key, rid):
    m = MASTERS.get(key)
    if not m:
        abort(404)
    try:
        run(f"DELETE FROM {m['table']} WHERE {m['pk']} = %s", (rid,))
        flash("Record deleted.", "success")
    except Exception as e:
        flash(friendly(e), "danger")
    return redirect(url_for("master", key=key))


@app.route("/cases/<int:cid>/delete", methods=["POST"])
def case_delete(cid):
    def work(cur):
        cur.execute("DELETE FROM case_person WHERE case_id=%s", (cid,))
        cur.execute("DELETE FROM case_file WHERE case_id=%s", (cid,))
    try:
        tx(work)
        flash("Case deleted.", "success")
    except Exception as e:
        flash(friendly(e), "danger")
    return redirect(url_for("cases"))


@app.route("/orders/<int:oid>/delete", methods=["POST"])
def order_delete(oid):
    def work(cur):
        cur.execute("DELETE FROM court_order_property WHERE order_id=%s", (oid,))
        cur.execute("DELETE FROM court_order WHERE order_id=%s", (oid,))
    try:
        tx(work)
        flash("Court order deleted.", "success")
    except Exception as e:
        flash(friendly(e), "danger")
    return redirect(url_for("orders"))


# ---------------------------------------------------------------------
# DELETE PROPERTY (for mistaken entries). A copy of every deleted custody
# row is written to audit_log first; the property row itself is logged by
# the audit trigger.
# ---------------------------------------------------------------------
MIGRATE_SQL = """CREATE OR REPLACE FUNCTION fn_block_txn_change() RETURNS trigger AS $$
BEGIN
  -- the app may delete a mistaken property together with its history
  -- (it sets malkhana.allow_cleanup = 'on' and writes a copy to audit_log first)
  IF TG_OP = 'DELETE' AND current_setting('malkhana.allow_cleanup', true) = 'on' THEN
    RETURN OLD;
  END IF;
  RAISE EXCEPTION 'custody_txn is append-only; corrections need a new entry';
END; $$ LANGUAGE plpgsql;"""


def migrate():
    """Updates the custody trigger in an existing database (safe to run many times)."""
    try:
        run(MIGRATE_SQL)
    except Exception as e:
        print("Note: could not update the custody trigger:", e)


@app.route("/property/<int:pid>/delete", methods=["POST"])
def property_delete(pid):
    def work(cur):
        cur.execute("SET LOCAL malkhana.allow_cleanup = 'on'")
        cur.execute("""INSERT INTO audit_log (table_name, record_id, action, old_data)
                       SELECT 'custody_txn', txn_id::text, 'DELETE', to_jsonb(t)
                       FROM custody_txn t WHERE property_id=%s""", (pid,))
        for stmt in ("DELETE FROM custody_txn WHERE property_id=%s",
                     "DELETE FROM fsl_request WHERE property_id=%s",
                     "DELETE FROM disposal WHERE property_id=%s",
                     "DELETE FROM court_order_property WHERE property_id=%s",
                     "DELETE FROM property_claim WHERE property_id=%s",
                     "DELETE FROM inspection_item WHERE property_id=%s"):
            cur.execute(stmt, (pid,))
        cur.execute("DELETE FROM property WHERE property_id=%s", (pid,))
        if cur.rowcount == 0:
            raise ValueError("Property not found.")
    try:
        tx(work)
        flash("Property and its custody history deleted. A copy is kept in the Audit Log.", "success")
    except Exception as e:
        flash(friendly(e), "danger")
        return redirect(url_for("property_detail", pid=pid))
    return redirect(url_for("property_list"))

# ---------------------------------------------------------------------
# 8. AUDIT LOG
# ---------------------------------------------------------------------
@app.route("/audit")
def audit():
    rows = run("""SELECT log_id AS "ID", to_char(logged_at,'DD-Mon-YYYY HH24:MI:SS') AS "Time",
                  table_name AS "Table", record_id AS "Record", action AS "Action"
                  FROM audit_log ORDER BY log_id DESC LIMIT 100""")
    return render_template("audit.html", rows=rows)


if __name__ == "__main__":
    if DB["password"] == "YOUR_PASSWORD_HERE":
        DB["password"] = getpass.getpass("Enter YOUR PostgreSQL password (typing is hidden): ")
    migrate()
    seed_demo_users()
    app.run(debug=os.getenv("FLASK_DEBUG") == "1", use_reloader=False)
