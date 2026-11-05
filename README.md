# Malkhana Management System

A DBMS project that tracks police case property (the *malkhana* storeroom):
what was seized, where it is stored, who handled it, and what finally happened to it.

**Tech stack:** PostgreSQL (database) + Python Flask (backend) + HTML/Bootstrap (frontend)

## Features
- 27-table normalized (3NF) PostgreSQL schema with an EER specialization:
  `property` is the supertype with 5 subtypes (arms, narcotics, vehicle, cash/valuables, electronic)
- Chain of custody ledger (append-only, protected by a trigger)
- Court order required for release or disposal (CHECK constraint)
- Automatic status/location updates and audit log (triggers)
- Web app: dashboard, cases, property register, move property, court orders, master data, audit log

## Project structure
```
app.py              Flask backend
templates/          HTML pages
database/schema.sql                   creates all tables, triggers and views
database/sample_data_and_queries.sql  demo data and example queries
requirements.txt    Python packages
```

## How to run (for anyone who downloads this)
You only need **PostgreSQL** and **Python 3**. Nobody needs the original author's password:
use the password of **your own** PostgreSQL (the one you set while installing it).

1. Install PostgreSQL (postgresql.org) and Python 3 (python.org, tick "Add python.exe to PATH").
2. Download this repository (green **Code** button > **Download ZIP**) and extract it.
3. **Windows quick way:** double-click `setup.bat` (enter your PostgreSQL password when asked),
   then double-click `run.bat` (enter the password again).
4. **Or type these in a terminal inside the folder:**
   ```
   pip install -r requirements.txt
   python setup_db.py
   python app.py
   ```
5. Open http://127.0.0.1:5000

`setup_db.py` creates the database `malkhana_db`, all 27 tables, triggers, views and demo data.
Running it again resets the demo data.

### Troubleshooting
| Message | Fix |
|---|---|
| `password authentication failed` | Wrong PostgreSQL password. Type the one you set at install time. |
| `could not connect to server` | PostgreSQL is not running. Start it (Services > postgresql). |
| `No module named flask` | Run `pip install -r requirements.txt` |

## How to understand the project
1. Read the **Project structure** above.
2. Open `database/schema.sql` to see the tables and rules (CHECK constraints and triggers).
3. Run the app and click: Dashboard > Property > Open an item > Move this property.
4. Try releasing an item without a court order: the database rejects it.

## Team
Add your names here.
