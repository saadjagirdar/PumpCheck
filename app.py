import streamlit as st
import sqlite3
import pandas as pd
from datetime import date, datetime
from pathlib import Path

APP_DIR = Path(__file__).parent
DB_PATH = APP_DIR / "pumpcheck.db"

st.set_page_config(page_title="PumpCheck", page_icon="⛽", layout="wide")

def connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS attendants (
            attendant_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS shifts (
            shift_id INTEGER PRIMARY KEY AUTOINCREMENT,
            shift_date TEXT NOT NULL,
            shift_name TEXT NOT NULL,
            attendant_id INTEGER NOT NULL,
            nozzle_id TEXT NOT NULL,
            fuel_type TEXT NOT NULL,
            opening_reading REAL NOT NULL,
            closing_reading REAL NOT NULL,
            rate_per_litre REAL NOT NULL,
            cash_amount REAL NOT NULL DEFAULT 0,
            upi_amount REAL NOT NULL DEFAULT 0,
            card_amount REAL NOT NULL DEFAULT 0,
            notes TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(attendant_id) REFERENCES attendants(attendant_id),
            CHECK(closing_reading >= opening_reading),
            CHECK(rate_per_litre >= 0),
            CHECK(cash_amount >= 0 AND upi_amount >= 0 AND card_amount >= 0)
        );
        """)
        count = con.execute("SELECT COUNT(*) FROM attendants").fetchone()[0]
        if count == 0:
            con.executemany("INSERT INTO attendants(name) VALUES (?)",
                            [("Demo Attendant A",), ("Demo Attendant B",)])
        con.commit()

def query_df(sql, params=()):
    with connect() as con:
        return pd.read_sql_query(sql, con, params=params)

def add_shift(shift_date, shift_name, attendant_id, nozzle_id, fuel_type,
              opening, closing, rate, cash, upi, card, notes):
    with connect() as con:
        con.execute("""INSERT INTO shifts
        (shift_date, shift_name, attendant_id, nozzle_id, fuel_type, opening_reading,
         closing_reading, rate_per_litre, cash_amount, upi_amount, card_amount, notes)
         VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
         (str(shift_date), shift_name, attendant_id, nozzle_id, fuel_type,
          opening, closing, rate, cash, upi, card, notes))
        con.commit()

init_db()
st.title("⛽ PumpCheck")
st.caption("Petrol Pump Sales & Shift Record System | Academic demonstration project")
st.info("Demo app: use fictional/sample records for testing. Do not enter customer personal data or confidential pump records.")

with st.sidebar:
    st.header("Navigation")
    page = st.radio("Open module", ["Dashboard", "Add Shift Record", "Shift Records", "Reports", "About & Field Study"])
    st.divider()
    st.caption("Local prototype · SQLite database")

if page == "Dashboard":
    shifts = query_df("""SELECT s.*, a.name AS attendant FROM shifts s
                         JOIN attendants a ON a.attendant_id=s.attendant_id""")
    if shifts.empty:
        st.subheader("Dashboard")
        st.write("No shift records yet. Add a sample shift record to see the dashboard.")
        st.metric("Recorded shifts", 0)
        st.metric("Recorded fuel volume", "0.00 L")
        st.metric("Recorded sales value", "₹0.00")
    else:
        shifts["litres_sold"] = shifts["closing_reading"] - shifts["opening_reading"]
        shifts["expected_sales"] = shifts["litres_sold"] * shifts["rate_per_litre"]
        shifts["collected"] = shifts["cash_amount"] + shifts["upi_amount"] + shifts["card_amount"]
        shifts["difference"] = shifts["expected_sales"] - shifts["collected"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Recorded shifts", f"{len(shifts)}")
        c2.metric("Fuel volume", f"{shifts['litres_sold'].sum():,.2f} L")
        c3.metric("Expected sales", f"₹{shifts['expected_sales'].sum():,.2f}")
        c4.metric("Collection difference", f"₹{shifts['difference'].sum():,.2f}")
        st.subheader("Sales by date")
        by_date = shifts.groupby("shift_date", as_index=False)["expected_sales"].sum()
        st.bar_chart(by_date.set_index("shift_date"))
        st.subheader("Recent records")
        st.dataframe(shifts[["shift_date","shift_name","attendant","nozzle_id","fuel_type",
                             "litres_sold","expected_sales","collected","difference"]]
                     .sort_values("shift_date", ascending=False).head(10), use_container_width=True)
        st.caption("Expected sales are calculated from meter difference × rate. Actual pump accounting may require additional adjustments.")

elif page == "Add Shift Record":
    st.subheader("Add a Shift Record")
    attendants = query_df("SELECT attendant_id, name FROM attendants WHERE active=1 ORDER BY name")
    with st.form("shift_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        shift_date = c1.date_input("Shift date", value=date.today())
        shift_name = c2.selectbox("Shift", ["Morning", "Afternoon", "Night"])
        attendant_map = dict(zip(attendants["name"], attendants["attendant_id"]))
        attendant_name = st.selectbox("Attendant", list(attendant_map.keys()))
        c3, c4, c5 = st.columns(3)
        nozzle_id = c3.text_input("Nozzle / dispenser ID", placeholder="e.g. N-01")
        fuel_type = c4.selectbox("Fuel type", ["Petrol", "Diesel", "Other"])
        rate = c5.number_input("Rate per litre (₹)", min_value=0.0, value=100.0, step=0.1)
        c6, c7 = st.columns(2)
        opening = c6.number_input("Opening meter reading", min_value=0.0, value=10000.0, step=0.1)
        closing = c7.number_input("Closing meter reading", min_value=0.0, value=10010.0, step=0.1)
        st.markdown("**Collection split (₹)**")
        c8, c9, c10 = st.columns(3)
        cash = c8.number_input("Cash", min_value=0.0, value=1000.0, step=10.0)
        upi = c9.number_input("UPI", min_value=0.0, value=0.0, step=10.0)
        card = c10.number_input("Card", min_value=0.0, value=0.0, step=10.0)
        notes = st.text_area("Notes (optional)", max_chars=300)
        submitted = st.form_submit_button("Save shift record", type="primary")
        if submitted:
            if not nozzle_id.strip():
                st.error("Please enter a nozzle / dispenser ID.")
            elif closing < opening:
                st.error("Closing reading cannot be lower than opening reading.")
            else:
                try:
                    add_shift(shift_date, shift_name, attendant_map[attendant_name], nozzle_id.strip(),
                              fuel_type, opening, closing, rate, cash, upi, card, notes.strip())
                    litres = closing - opening
                    expected = litres * rate
                    collected = cash + upi + card
                    st.success(f"Saved. Meter difference: {litres:.2f} L · Expected sales: ₹{expected:,.2f} · Recorded collection: ₹{collected:,.2f}")
                except Exception as e:
                    st.error(f"Could not save record: {e}")

elif page == "Shift Records":
    st.subheader("Shift Records")
    df = query_df("""SELECT s.shift_id, s.shift_date, s.shift_name, a.name AS attendant,
                     s.nozzle_id, s.fuel_type, s.opening_reading, s.closing_reading,
                     (s.closing_reading-s.opening_reading) AS litres_sold,
                     s.rate_per_litre,
                     (s.closing_reading-s.opening_reading)*s.rate_per_litre AS expected_sales,
                     s.cash_amount, s.upi_amount, s.card_amount,
                     (s.cash_amount+s.upi_amount+s.card_amount) AS total_collection,
                     ((s.closing_reading-s.opening_reading)*s.rate_per_litre)-
                     (s.cash_amount+s.upi_amount+s.card_amount) AS difference, s.notes
                     FROM shifts s JOIN attendants a ON a.attendant_id=s.attendant_id
                     ORDER BY s.shift_date DESC, s.shift_id DESC""")
    if df.empty:
        st.warning("No records available yet.")
    else:
        min_date = pd.to_datetime(df["shift_date"]).min().date()
        max_date = pd.to_datetime(df["shift_date"]).max().date()
        d1, d2 = st.columns(2)
        start = d1.date_input("From", value=min_date)
        end = d2.date_input("To", value=max_date)
        filtered = df[(pd.to_datetime(df["shift_date"]).dt.date >= start) &
                      (pd.to_datetime(df["shift_date"]).dt.date <= end)]
        st.dataframe(filtered, use_container_width=True, hide_index=True)
        st.download_button("Download CSV", filtered.to_csv(index=False).encode("utf-8"),
                           file_name="pumpcheck_shift_records.csv", mime="text/csv")

elif page == "Reports":
    st.subheader("Reports & Reconciliation")
    df = query_df("""SELECT s.shift_date, s.shift_name, a.name AS attendant, s.fuel_type,
                     (s.closing_reading-s.opening_reading) AS litres_sold,
                     (s.closing_reading-s.opening_reading)*s.rate_per_litre AS expected_sales,
                     (s.cash_amount+s.upi_amount+s.card_amount) AS total_collection,
                     ((s.closing_reading-s.opening_reading)*s.rate_per_litre)-
                     (s.cash_amount+s.upi_amount+s.card_amount) AS difference
                     FROM shifts s JOIN attendants a ON a.attendant_id=s.attendant_id
                     ORDER BY s.shift_date""")
    if df.empty:
        st.write("Add records first to generate reports.")
    else:
        c1, c2 = st.columns(2)
        c1.metric("Total litres", f"{df['litres_sold'].sum():,.2f}")
        c2.metric("Expected sales", f"₹{df['expected_sales'].sum():,.2f}")
        st.bar_chart(df.groupby("fuel_type")["litres_sold"].sum())
        st.dataframe(df.groupby("shift_date", as_index=False)[
            ["litres_sold","expected_sales","total_collection","difference"]].sum(),
            use_container_width=True, hide_index=True)
        st.download_button("Download report CSV", df.to_csv(index=False).encode("utf-8"),
                           file_name="pumpcheck_report.csv", mime="text/csv")

else:
    st.subheader("About PumpCheck")
    st.markdown("""
    **Purpose:** Demonstrate how a small petrol pump could record shift-level meter readings,
    estimate sales, record payment modes and review differences.

    **Important limitations**
    - This is an academic prototype, not a certified fuel retail or accounting system.
    - It does not connect to real dispensing machines, payment gateways, or oil-company systems.
    - It does not replace official meter records, statutory accounting, or safety procedures.
    - Sample attendants and default values are fictional. Replace or remove them for your demonstration.
    """)
    st.markdown("### Field study checklist")
    st.write("1. Ask the pump manager for permission.")
    st.write("2. Ask how shift records and payment totals are currently reconciled.")
    st.write("3. Observe only the process you are permitted to observe.")
    st.write("4. Record actual findings separately; do not photograph confidential screens or customer details.")
    st.write("5. Obtain the required organization certificate if the guide requires it.")

st.caption("PumpCheck · BCA Field Project prototype · Keep real operational data confidential.")
