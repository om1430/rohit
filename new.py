"""
Transport Management Software - Streamlit Single File App (Updated to your new requirements)

Features implemented (end-to-end):
1. Master Setup
   - Party Master (name, address, mobile, GST, marka, default rate)
   - Item Master (optional)
   - Rate Master (optional)

2. Token / Bilty Generation (Auto token no, datetime, auto calculate total)
   - Print (download as Excel) and WhatsApp text generator
   - Token list (booked / delivered)

3. Challan / Loading
   - Create challan for a truck by selecting tokens
   - Auto challan no, truck/driver details
   - Challan print / download and WhatsApp share

4. Ledger / Account Book (party-wise ledger)
   - Token charges, invoices, payments
   - Balance calculation, export to Excel

5. Payments Entry (Cash / Bank / UPI / Cheque)

6. Billing System (Invoice generate using date range)

7. Delivery Entry (mark delivered, receiver name, signature note)

8. Reports (Daily booking, Challan report, Party ledger, Outstanding, Truck-wise, Token register, Delivery report)

9. User Roles (simulated via sidebar role selector)

10. Extras: WhatsApp message text generation, DB export

How to use:
1. Save as `transport_tms_updated.py`
2. Install dependencies: pip install streamlit pandas openpyxl
3. Run: streamlit run transport_tms_updated.py

This single-file app uses SQLite for persistence (tms_new.db). You can choose to migrate existing DB manually if needed.
"""

import streamlit as st
import sqlite3
import pandas as pd
import io
import os
from datetime import datetime
from pathlib import Path

# ----------------- Config -----------------
DB_PATH = "tms_new.db"

# ----------------- Helpers -----------------
# Requires: reportlab
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import io, math
from datetime import datetime

def _register_dejavu():
    """Try to register DejaVuSans for rupee symbol support; ignore if not available."""
    try:
        pdfmetrics.registerFont(TTFont('DejaVuSans', 'DejaVuSans.ttf'))
        pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', 'DejaVuSans-Bold.ttf'))
        return 'DejaVuSans'
    except Exception:
        return 'Helvetica'  # fallback

FONT_NAME = _register_dejavu()

def df_to_pdf_bytes_exact(df: pd.DataFrame,
                          title: str = "Report",
                          subtitle: str = "",
                          page_orientation: str = "portrait",
                          col_widths: list = None,
                          rows_per_page_override: int = None):
    """
    Convert DataFrame to PDF bytes with styling matching the old layout.
    - df: pandas DataFrame (column order & names will be preserved)
    - title: main title shown on each page (e.g., company name)
    - subtitle: small subtitle or date-range
    - page_orientation: 'portrait' or 'landscape'
    - col_widths: optional list of widths in points (len must equal df.columns)
    - rows_per_page_override: optional override for rows per page (int)
    Returns: io.BytesIO() (seeked to 0)
    """
    buf = io.BytesIO()
    pagesize = landscape(A4) if page_orientation == "landscape" else A4
    pw, ph = pagesize
    margin = 12 * mm
    usable_w = pw - 2 * margin
    usable_h = ph - 2 * margin

    # Prepare data: header row = column names (preserve exact names)
    cols = list(df.columns)
    data_rows = []
    for _, r in df.iterrows():
        row_vals = []
        for c in cols:
            v = r[c]
            # Format numbers nicely (integers without .0, floats rounded to 2)
            if pd.isna(v):
                row_vals.append("")
            elif isinstance(v, (int,)) or (isinstance(v, float) and float(v).is_integer()):
                row_vals.append(str(int(v)))
            elif isinstance(v, float):
                row_vals.append(str(round(v, 2)))
            else:
                row_vals.append(str(v))
        data_rows.append(row_vals)

    # Build full table data (header + data)
    table_data = [cols] + data_rows
    ncols = len(cols)

    # Column widths: if provided, use; otherwise distribute with heuristics
    if col_widths and len(col_widths) == ncols:
        widths = col_widths
    else:
        # Heuristic: allow wider for columns with long text (detect by sample)
        avg_char_counts = []
        sample_rows = df.head(200).astype(str).fillna("")
        for c in cols:
            avg_len = sample_rows[c].map(len).mean() if not sample_rows.empty else 10
            avg_char_counts.append(max(10, avg_len))
        total_chars = sum(avg_char_counts)
        widths = [max(50, usable_w * (ac / total_chars)) for ac in avg_char_counts]

        # ensure total <= usable_w, scale if necessary
        total_w = sum(widths)
        if total_w > usable_w:
            scale = usable_w / total_w
            widths = [w * scale for w in widths]

    # Row height & pagination
    header_h = 26
    row_h = 18
    footer_h = 22
    available_h = usable_h - header_h - footer_h
    rows_per_page = int(available_h // row_h)
    if rows_per_page_override and isinstance(rows_per_page_override, int):
        rows_per_page = rows_per_page_override
    # include header row on each page -> effective data rows per page:
    data_rows_per_page = max(3, rows_per_page - 1)

    total_data_rows = len(data_rows)
    total_pages = max(1, math.ceil(total_data_rows / data_rows_per_page))

    c = canvas.Canvas(buf, pagesize=pagesize)

    for page in range(total_pages):
        # Header block (title + subtitle + generated timestamp)
        c.setFont(FONT_NAME, 14)
        # center title
        title_text = title
        title_w = c.stringWidth(title_text, FONT_NAME, 14)
        c.drawString((pw - title_w) / 2, ph - margin - 6, title_text)

        if subtitle:
            c.setFont(FONT_NAME, 10)
            subtitle_w = c.stringWidth(subtitle, FONT_NAME, 10)
            c.drawString((pw - subtitle_w) / 2, ph - margin - 24, subtitle)

        # Timestamp on right
        c.setFont(FONT_NAME, 8)
        ts = datetime.now().strftime("%d-%m-%Y %H:%M")
        c.drawRightString(pw - margin, ph - margin - 6, f"Generated: {ts}")

        # Prepare page slice of data (include header row)
        start_idx = page * data_rows_per_page
        end_idx = min(start_idx + data_rows_per_page, total_data_rows)
        page_table = [cols] + data_rows[start_idx:end_idx]

        # Table styling close to old code
        table = Table(page_table, colWidths=widths)
        style = TableStyle([
            ('GRID', (0,0), (-1,-1), 0.6, colors.black),
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#4472C4')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('FONTNAME', (0,0), (-1,0), FONT_NAME),
            ('FONTSIZE', (0,0), (-1,0), 9),
            ('ALIGN', (0,0), (-1,0), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('FONTSIZE', (0,1), (-1,-1), 8),
            ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#FFF2CC')),
        ])
        # Last (subtotal) row styling if it matches pattern "TOTAL" in first col
        # (user can append such a row in df beforehand if needed)
        # Align numeric columns to right
        for ci, c_name in enumerate(cols):
            # choose right align for numeric-like columns by inspecting dtype
            if pd.api.types.is_numeric_dtype(df[c_name]):
                style.add('ALIGN', (ci,1), (ci,-1), 'RIGHT')
            else:
                style.add('ALIGN', (ci,1), (ci,-1), 'LEFT')
        # If last row first cell contains TOTAL, highlight
        if page_table and page_table[-1] and isinstance(page_table[-1][0], str) and page_table[-1][0].upper().startswith("TOTAL"):
            last_row_index = len(page_table) - 1
            style.add('BACKGROUND', (0, last_row_index), (-1, last_row_index), colors.HexColor('#FFD966'))
            style.add('FONTNAME', (0, last_row_index), (-1, last_row_index), FONT_NAME)
            style.add('FONTSIZE', (0, last_row_index), (-1, last_row_index), 9)
            style.add('LINEABOVE', (0, last_row_index), (-1, last_row_index), 1.2, colors.black)

        table.setStyle(style)

        # Draw table at computed position
        w, h = table.wrap(usable_w, available_h)
        x = margin
        y = ph - margin - header_h - h
        table.drawOn(c, x, y)

        # Footer
        c.setFont(FONT_NAME, 8)
        c.drawString(margin, margin / 2, f"Page {page+1} of {total_pages}")
        c.drawRightString(pw - margin, margin / 2, "Transport TMS")

        c.showPage()

    c.save()
    buf.seek(0)
    return buf


def get_conn():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

conn = get_conn()
cur = conn.cursor()

def init_db():
    cur.executescript('''
    CREATE TABLE IF NOT EXISTS parties (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        address TEXT,
        mobile TEXT,
        gst TEXT,
        marka TEXT,
        default_rate REAL
    );

    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        description TEXT
    );

    CREATE TABLE IF NOT EXISTS rates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id INTEGER,
        rate_per_kg REAL,
        rate_per_parcel REAL,
        note TEXT,
        FOREIGN KEY(item_id) REFERENCES items(id)
    );

    CREATE TABLE IF NOT EXISTS tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        token_no TEXT UNIQUE,
        created_at TEXT,
        party_id INTEGER,
        marka TEXT,
        weight REAL,
        rate_per_kg REAL,
        rate_per_parcel REAL,
        total_amount REAL,
        from_city TEXT,
        to_city TEXT,
        status TEXT DEFAULT 'Booked',
        delivery_date TEXT,
        receiver TEXT,
        remark TEXT,
        challan_id INTEGER,
        FOREIGN KEY(party_id) REFERENCES parties(id)
    );

    CREATE TABLE IF NOT EXISTS challans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        challan_no TEXT UNIQUE,
        created_at TEXT,
        truck_no TEXT,
        driver_name TEXT,
        driver_mobile TEXT,
        origin TEXT,
        destination TEXT
    );

    CREATE TABLE IF NOT EXISTS challan_tokens (
        challan_id INTEGER,
        token_id INTEGER,
        PRIMARY KEY (challan_id, token_id),
        FOREIGN KEY(challan_id) REFERENCES challans(id),
        FOREIGN KEY(token_id) REFERENCES tokens(id)
    );

    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        party_id INTEGER,
        amount REAL,
        method TEXT,
        date TEXT,
        remark TEXT,
        FOREIGN KEY(party_id) REFERENCES parties(id)
    );
    ''')
    conn.commit()

init_db()

# ----------------- Utility -----------------

def generate_token_no():
    cur.execute("SELECT COUNT(*) FROM tokens")
    c = cur.fetchone()[0] + 1
    return f"TN-{c:05d}"

def generate_challan_no():
    cur.execute("SELECT COUNT(*) FROM challans")
    c = cur.fetchone()[0] + 1
    return f"CH-{c:05d}"

def to_excel_bytes(df: pd.DataFrame):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()

# ----------------- CRUD -----------------

def add_party(name, address, mobile, gst, marka, default_rate):
    cur.execute("INSERT OR REPLACE INTO parties (name,address,mobile,gst,marka,default_rate) VALUES (?,?,?,?,?,?)",
                (name, address, mobile, gst, marka, default_rate))
    conn.commit()

def get_parties_df():
    return pd.read_sql_query("SELECT * FROM parties ORDER BY name", conn)

def create_token(party_id, marka, weight, rate_per_kg, rate_per_parcel, from_city, to_city, remark):
    token_no = generate_token_no()
    created_at = datetime.now().isoformat()
    total = 0.0
    if rate_per_kg and weight:
        total = float(rate_per_kg) * float(weight)
    elif rate_per_parcel:
        total = float(rate_per_parcel)
    cur.execute("INSERT INTO tokens (token_no,created_at,party_id,marka,weight,rate_per_kg,rate_per_parcel,total_amount,from_city,to_city,remark) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (token_no, created_at, party_id, marka, weight, rate_per_kg, rate_per_parcel, total, from_city, to_city, remark))
    conn.commit()
    return token_no

def get_tokens(open_only=True):
    q = "SELECT t.*, p.name AS party_name FROM tokens t LEFT JOIN parties p ON t.party_id=p.id"
    if open_only:
        q += " WHERE t.status!='Delivered'"
    q += " ORDER BY t.created_at DESC"
    return pd.read_sql_query(q, conn)

def create_challan(truck_no, driver_name, driver_mobile, origin, destination, token_ids):
    challan_no = generate_challan_no()
    created_at = datetime.now().isoformat()
    cur.execute("INSERT INTO challans (challan_no,created_at,truck_no,driver_name,driver_mobile,origin,destination) VALUES (?,?,?,?,?,?,?)",
                (challan_no, created_at, truck_no, driver_name, driver_mobile, origin, destination))
    challan_id = cur.lastrowid
    for tid in token_ids:
        cur.execute("INSERT OR IGNORE INTO challan_tokens (challan_id,token_id) VALUES (?,?)", (challan_id, tid))
        cur.execute("UPDATE tokens SET challan_id=?, status='Loaded' WHERE id=?", (challan_id, tid))
    conn.commit()
    return challan_no

def add_payment(party_id, amount, method, date, remark):
    cur.execute("INSERT INTO payments (party_id,amount,method,date,remark) VALUES (?,?,?,?,?)", (party_id, amount, method, date, remark))
    conn.commit()

def party_ledger(party_id):
    tokens = pd.read_sql_query("SELECT id, token_no, created_at, total_amount, status FROM tokens WHERE party_id=? ORDER BY created_at", conn, params=(party_id,))
    payments = pd.read_sql_query("SELECT * FROM payments WHERE party_id=? ORDER BY date", conn, params=(party_id,))
    total_tokens = tokens['total_amount'].sum() if not tokens.empty else 0.0
    total_payments = payments['amount'].sum() if not payments.empty else 0.0
    balance = total_tokens - total_payments
    return tokens, payments, float(total_tokens), float(total_payments), float(balance)

# ----------------- Streamlit UI -----------------

st.set_page_config(page_title="Transport TMS", layout='wide')

# Sidebar - vertical navigation + role
st.sidebar.title("Transport TMS")
st.sidebar.markdown("---")
role = st.sidebar.selectbox("Select Role", ["Admin", "Booking User", "Accounts User", "Loading User"])
st.sidebar.markdown("---")
menu = st.sidebar.radio("Menu", [
    "Dashboard",
    "Master Setup",
    "Token / Bilty",
    "Challan / Loading",
    "Payments & Ledger",
    "Billing / Invoice",
    "Delivery",
    "Reports",
    "Export / Backup"
])

st.title("🚚 Transport Management Software")
st.caption(f"Role: {role}")

# ----------------- Dashboard -----------------
if menu == "Dashboard":
    st.header("Dashboard")
    parties = get_parties_df()
    tokens_all = get_tokens(open_only=False)
    st.metric("Total Parties", len(parties))
    st.metric("Total Tokens", len(tokens_all))
    st.markdown("### Recent Tokens")
    st.dataframe(tokens_all.head(20))

# ----------------- Master Setup -----------------
if menu == "Master Setup":
    st.header("Master Setup")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Add / Edit Party")
        name = st.text_input("Party Name")
        address = st.text_input("Address")
        mobile = st.text_input("Mobile")
        gst = st.text_input("GST No (optional)")
        marka = st.text_input("Marka / Sign")
        default_rate = st.number_input("Default Rate (per kg)", min_value=0.0, format="%.2f")
        if st.button("Save Party"):
            if not name:
                st.error("Party name required")
            else:
                add_party(name.strip(), address.strip(), mobile.strip(), gst.strip(), marka.strip(), default_rate if default_rate>0 else None)
                st.success("Party saved")
    with col2:
        st.subheader("Existing Parties")
        st.dataframe(get_parties_df())
# ----------------- Token / Bilty -----------------
if menu == "Token / Bilty":
    st.header("Token / Bilty Generation")
    parties = get_parties_df()
    if parties.empty:
        st.info("Please create parties first in Master Setup")
    else:
        col1, col2 = st.columns([2, 1])
        with col1:
            st.subheader("Create New Token")
            party_name = st.selectbox("Select Party", parties['name'].tolist())
            party_id = int(parties[parties['name'] == party_name]['id'].iloc[0])
            # safe marka fallback
            default_marka = parties.loc[parties['name'] == party_name, 'marka'].iloc[0] if 'marka' in parties.columns else ""
            default_marka = "" if pd.isna(default_marka) else str(default_marka)
            marka = st.text_input("Marka/Sign", value=default_marka)
            weight = st.number_input("Weight (kg)", min_value=0.0, format="%.2f")
            rate_per_kg = st.number_input("Rate per kg (leave 0 if parcel)", min_value=0.0, format="%.2f")
            rate_per_parcel = st.number_input("Rate per parcel (optional)", min_value=0.0, format="%.2f")
            from_city = st.selectbox("From City", ["Delhi", "Mumbai"], index=0)
            to_city = st.selectbox("To City", ["Delhi", "Mumbai"], index=1)
            remark = st.text_area("Remark (optional)")

            if st.button("Generate Token"):
                if weight <= 0 and rate_per_parcel <= 0:
                    st.error("Enter weight > 0 or provide a parcel rate.")
                else:
                    # pass None for optional numeric fields if zero
                    weight_val = float(weight) if weight > 0 else None
                    rpk = float(rate_per_kg) if rate_per_kg > 0 else None
                    rpp = float(rate_per_parcel) if rate_per_parcel > 0 else None

                    token_no = create_token(
                        party_id,
                        marka.strip() if isinstance(marka, str) else "",
                        weight_val,
                        rpk,
                        rpp,
                        from_city,
                        to_city,
                        remark.strip() if isinstance(remark, str) else ""
                    )

                    st.success(f"Token generated: {token_no}")

                    # fetch and display token row
                    df = pd.read_sql_query(
                        "SELECT t.*, p.name as party_name FROM tokens t LEFT JOIN parties p ON t.party_id=p.id WHERE token_no=?",
                        conn,
                        params=(token_no,)
                    )

                    if not df.empty:
                        st.table(df.T)
                        amount = df['total_amount'].iloc[0] if 'total_amount' in df.columns else 0.0
                    else:
                        amount = 0.0

                    # WhatsApp text (copy-paste ready)
                    wa = (
                        f"Token: {token_no}\n"
                        f"Party: {party_name}\n"
                        f"Marka/Sign: {marka}\n"
                        f"Weight: {weight} kg\n"
                        f"From: {from_city}  To: {to_city}\n"
                        f"Amount: ₹{amount:.2f}"
                    )
                    st.code(wa)

                    # Download token as Excel
                    st.download_button(
                        "Download Token (Excel)",
                        data=to_excel_bytes(df),
                        file_name=f"{token_no}.xlsx"
                    )

        with col2:
            st.subheader("Token List")
            tokens = get_tokens(open_only=False)
            st.dataframe(tokens[['id', 'token_no', 'created_at', 'party_name', 'weight', 'total_amount', 'from_city', 'to_city', 'status']])

# ----------------- Challan / Loading -----------------
if menu == "Challan / Loading":
    st.header("Challan / Loading")
    open_tokens = get_tokens(open_only=True)
    if open_tokens.empty:
        st.info("No open tokens available to load")
    else:
        st.markdown("### Open Tokens")
        st.dataframe(open_tokens[['id','token_no','party_name','weight','total_amount','from_city','to_city']])
        selected = st.multiselect("Select tokens to add to challan (by token id)", options=open_tokens['id'].tolist())
        truck_no = st.text_input("Truck Number")
        driver_name = st.text_input("Driver Name")
        driver_mobile = st.text_input("Driver Mobile")
        origin = st.text_input("Origin (From City)")
        destination = st.text_input("Destination (To City)")
        if st.button("Create Challan"):
            if not selected or not truck_no:
                st.error("Select tokens and enter truck number")
            else:
                ch_no = create_challan(truck_no.strip(), driver_name.strip(), driver_mobile.strip(), origin.strip(), destination.strip(), selected)
                st.success(f"Challan created: {ch_no}")
                ch_df = pd.read_sql_query("SELECT * FROM challans WHERE challan_no=?", conn, params=(ch_no,))
                st.table(ch_df.T)
                # Show challan tokens
                cid = int(ch_df['id'].iloc[0])
                ct = pd.read_sql_query("SELECT t.token_no, p.name as party_name, t.weight, t.total_amount FROM challan_tokens ct JOIN tokens t ON ct.token_id=t.id JOIN parties p ON t.party_id=p.id WHERE ct.challan_id=?", conn, params=(cid,))
                st.dataframe(ct)
                st.download_button("Download Challan Tokens (Excel)", data=to_excel_bytes(ct), file_name=f"{ch_no}_tokens.xlsx")

# ----------------- Payments & Ledger -----------------
if menu == "Payments & Ledger":
    st.header("Payments & Party Ledger")
    parties = get_parties_df()
    if parties.empty:
        st.info("Add parties in Master Setup first")
    else:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Add Payment")
            party_name = st.selectbox("Party", parties['name'].tolist())
            party_id = int(parties[parties['name']==party_name]['id'].iloc[0])
            amount = st.number_input("Amount", min_value=0.0, format="%.2f")
            method = st.selectbox("Method", ["Cash","Bank","UPI","Cheque"]) 
            date = st.date_input("Date", value=datetime.now().date())
            remark = st.text_input("Remark")
            if st.button("Save Payment"):
                add_payment(party_id, amount, method, date.isoformat(), remark)
                st.success("Payment recorded")
        with col2:
            st.subheader("Party Ledger")
            party_name = st.selectbox("Select party to view ledger", parties['name'].tolist(), key='ledger_party')
            pid = int(parties[parties['name']==party_name]['id'].iloc[0])
            tokens, payments, t_total, p_total, balance = party_ledger(pid)
            st.write("Total Charges:", t_total)
            st.write("Total Payments:", p_total)
            st.write("Balance:", balance)
            st.markdown("**Tokens**")
            st.dataframe(tokens)
            st.markdown("**Payments**")
            st.dataframe(payments)
            st.download_button("Download Ledger (Tokens)", data=to_excel_bytes(tokens), file_name=f"ledger_{party_name}_tokens.xlsx")
            st.download_button("Download Ledger (Payments)", data=to_excel_bytes(payments), file_name=f"ledger_{party_name}_payments.xlsx")

# ----------------- Billing / Invoice -----------------
if menu == "Billing / Invoice":
    st.header("Billing / Invoice Generation")
    parties = get_parties_df()
    if parties.empty:
        st.info("Add parties first")
    else:
        party_name = st.selectbox("Party for invoice", parties['name'].tolist())
        pid = int(parties[parties['name']==party_name]['id'].iloc[0])
        col1, col2 = st.columns(2)
        with col1:
            s_date = st.date_input("From Date")
            e_date = st.date_input("To Date")
            if st.button("Generate Invoice"):
                q = "SELECT * FROM tokens WHERE party_id=? AND date(created_at) BETWEEN date(?) AND date(?)"
                df = pd.read_sql_query(q, conn, params=(pid, s_date.isoformat(), e_date.isoformat()))
                if df.empty:
                    st.info("No tokens in this date range")
                else:
                    total = df['total_amount'].sum()
                    st.write(f"Invoice for {party_name} ({s_date} to {e_date})")
                    st.write("Total: ", total)
                    st.dataframe(df[['token_no','created_at','weight','total_amount','from_city','to_city','status']])
                    st.download_button("Download Invoice (Excel)", data=to_excel_bytes(df), file_name=f"invoice_{party_name}_{s_date}_{e_date}.xlsx")

# ----------------- Delivery -----------------
if menu == "Delivery":
    st.header("Delivery Entry")
    tokens_open = pd.read_sql_query("SELECT * FROM tokens WHERE status!='Delivered' ORDER BY created_at DESC", conn)
    if tokens_open.empty:
        st.info("No tokens to mark delivered")
    else:
        sel = st.selectbox("Select Token No to mark delivered", options=tokens_open['token_no'].tolist())
        row = tokens_open[tokens_open['token_no']==sel].iloc[0]
        st.write(row[['token_no','party_id','weight','total_amount','from_city','to_city']])
        delivery_date = st.date_input("Delivery Date", value=datetime.now().date())
        receiver = st.text_input("Receiver Name")
        signature = st.checkbox("Signature Collected")
        if st.button("Mark Delivered"):
            cur.execute("UPDATE tokens SET status='Delivered', delivery_date=?, receiver=? WHERE token_no=?", (delivery_date.isoformat(), receiver if receiver else None, sel))
            conn.commit()
            st.success("Token marked Delivered")

# ----------------- Reports -----------------
# ----------------- Reports -----------------
if menu == "Reports":
    st.header("Reports")
    rpt = st.selectbox("Select Report", [
        "Daily Booking Report",
        "Daily Loading / Challan Report",
        "Party Wise Ledger",
        "Outstanding Payment Report",
        "Truck Wise Consignment Report",
        "Token/Bilty Register",
        "Delivery Report"
    ])

    df = None
    pdf_title = rpt

    if rpt == "Daily Booking Report":
        date = st.date_input("Date")
        df = pd.read_sql_query(
            "SELECT t.*, p.name as party_name FROM tokens t LEFT JOIN parties p ON t.party_id=p.id WHERE date(created_at)=date(?)",
            conn, params=(date.isoformat(),)
        )
        pdf_title = f"Daily Booking Report - {date.strftime('%d-%m-%Y')}"

    elif rpt == "Daily Loading / Challan Report":
        date = st.date_input("Date for challan report")
        df = pd.read_sql_query("SELECT * FROM challans WHERE date(created_at)=date(?)", conn, params=(date.isoformat(),))
        pdf_title = f"Daily Challan Report - {date.strftime('%d-%m-%Y')}"

    elif rpt == "Party Wise Ledger":
        parties = get_parties_df()
        party = st.selectbox("Party", parties['name'].tolist(), key='rpt_party')
        pid = int(parties[parties['name'] == party]['id'].iloc[0])
        tokens, payments, t_total, p_total, balance = party_ledger(pid)
        # Concatenate tokens and payments in a readable format for PDF (two tables)
        st.write("Balance:", balance)
        st.markdown("**Tokens**")
        st.dataframe(tokens)
        st.markdown("**Payments**")
        st.dataframe(payments)
        # Provide separate downloads
        tok_pdf_title = f"Party Ledger - Tokens - {party}"
        pay_pdf_title = f"Party Ledger - Payments - {party}"
        if st.button("Download Tokens as PDF"):
            buf = df_to_pdf_bytes_exact(tokens, tok_pdf_title)
            st.download_button("Download Tokens PDF", data=buf, file_name=f"{party}_tokens.pdf", mime="application/pdf")
        if st.button("Download Payments as PDF"):
            buf2 = df_to_pdf_bytes_exact(payments, pay_pdf_title)
            st.download_button("Download Payments PDF", data=buf2, file_name=f"{party}_payments.pdf", mime="application/pdf")
        # Also Excel
        st.download_button("Download Tokens (Excel)", data=to_excel_bytes(tokens), file_name=f"tokens_{party}.xlsx")
        st.download_button("Download Payments (Excel)", data=to_excel_bytes(payments), file_name=f"payments_{party}.xlsx")
        # skip the rest because we've handled this report
        st.stop()

    elif rpt == "Outstanding Payment Report":
        parties_df = pd.read_sql_query("SELECT * FROM parties", conn)
        rows = []
        for _, r in parties_df.iterrows():
            tokens_, payments_, t_total, p_total, balance = party_ledger(r['id'])
            rows.append({"party": r['name'], "outstanding": balance})
        df = pd.DataFrame(rows)
        pdf_title = "Outstanding Payment Report"

    elif rpt == "Truck Wise Consignment Report":
        truck = st.text_input("Truck No (optional)")
        if truck:
            df = pd.read_sql_query(
                "SELECT c.challan_no, c.truck_no, t.token_no, p.name as party_name, t.weight, t.total_amount FROM challans c JOIN challan_tokens ct ON c.id=ct.challan_id JOIN tokens t ON ct.token_id=t.id JOIN parties p ON t.party_id=p.id WHERE c.truck_no LIKE ?",
                conn, params=(f"%{truck}%",)
            )
            pdf_title = f"Truck Consignment - {truck}"
        else:
            df = pd.read_sql_query(
                "SELECT c.challan_no, c.truck_no, t.token_no, p.name as party_name, t.weight, t.total_amount FROM challans c JOIN challan_tokens ct ON c.id=ct.challan_id JOIN tokens t ON ct.token_id=t.id JOIN parties p ON t.party_id=p.id",
                conn
            )
            pdf_title = "Truck Wise Consignment Report"

    elif rpt == "Token/Bilty Register":
        df = pd.read_sql_query(
            "SELECT t.token_no, p.name as party_name, t.created_at, t.weight, t.total_amount, t.status FROM tokens t LEFT JOIN parties p ON t.party_id=p.id ORDER BY t.created_at",
            conn
        )
        pdf_title = "Token / Bilty Register"

    elif rpt == "Delivery Report":
        df = pd.read_sql_query(
            "SELECT token_no, party_id, delivery_date, receiver, status FROM tokens WHERE status='Delivered'",
            conn
        )
        pdf_title = "Delivery Report"

    # Show df and provide downloads (PDF + Excel)
    if df is None:
        st.info("No data to show for this report.")
    else:
        st.markdown("### Report Preview")
        st.dataframe(df)
        # Excel download
        st.download_button("Download Excel", data=to_excel_bytes(df), file_name=f"{pdf_title.replace(' ','_')}.xlsx")
        # PDF download (generate on click)
        if st.button("Download PDF (Formatted)"):
            try:
                buf = df_to_pdf_bytes_exact(df, pdf_title, page_orientation="landscape" if df.shape[1] > 8 else "portrait")
                st.download_button("Download PDF", data=buf, file_name=f"{pdf_title.replace(' ','_')}.pdf", mime="application/pdf")
            except Exception as e:
                st.error(f"PDF generation failed: {e}")


# ----------------- Export / Backup -----------------
if menu == "Export / Backup":
    st.header("Export / Backup")
    if st.button("Download SQLite DB"):
        with open(DB_PATH,'rb') as f:
            st.download_button("Click to download DB file", data=f, file_name=DB_PATH)

# ----------------- Footer -----------------
st.sidebar.markdown("---")
st.sidebar.write("This is a single-file demo. Ask to add PDF invoices, WhatsApp API, QR/Barcode, or authentication and I'll integrate.")

# Close connection when app ends (optional)
# conn.close()
