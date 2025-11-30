import streamlit as st
import pandas as pd
import os
import io
import zipfile
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Table, TableStyle
from reportlab.lib import colors

# --- Custom CSS for professional look ---
st.markdown("""
<style>
    .main-header {
        text-align: center;
        padding: 2rem 0;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border-radius: 10px;
        margin-bottom: 2rem;
    }
    .feature-box {
        padding: 1.5rem;
        background: #f8f9fa;
        border-radius: 10px;
        border-left: 4px solid #667eea;
        margin: 1rem 0;
    }
    .stats-box {
        padding: 1rem;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border-radius: 10px;
        text-align: center;
    }
    .success-message {
        padding: 1rem;
        background: #d4edda;
        border-left: 4px solid #28a745;
        border-radius: 5px;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

# --- Utility Functions ---

def parse_date_flexible(date_str):
    if pd.isna(date_str): return pd.NaT
    date_str = str(date_str).strip()
    formats = ["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y"]
    for fmt in formats:
        try: return pd.to_datetime(date_str, format=fmt)
        except: continue
    try: return pd.to_datetime(date_str, dayfirst=True)
    except: return pd.NaT

def clean_city(x):
    if not isinstance(x, str): return ""
    x = x.upper().strip()
    x = x.replace(".", "").replace(",", "").replace("-", " ").strip()
    # Standardize city names
    if x in ["BOMBAY", "MUMBAI"]: return "MUMBAI"
    if x in ["DELHI"]: return "DELHI"
    return " ".join(x.split())

def clean_driver(x):
    if not isinstance(x, str): return "NA"
    x = x.upper().strip()
    if x in ["", "NA", "N/A", "NONE", "-", "--"]: return "NA"
    return " ".join(x.split())

def clean_consignor(x):
    if not isinstance(x, str): return ""
    x = x.upper().strip()
    return " ".join(x.split())

def clean_num(x):
    try:
        val = float(str(x).strip())
        return val if not pd.isna(val) else 0
    except: return 0

def get_week_info(date):
    """Returns week start date (Monday), end date (Sunday), and formatted range"""
    # Get the Monday of the week containing this date
    days_since_monday = date.weekday()  # Monday = 0, Sunday = 6
    week_start = date - pd.Timedelta(days=days_since_monday)
    week_end = week_start + pd.Timedelta(days=6)
    
    # Format: "DD MMM - DD MMM YYYY" (e.g., "20 Nov - 26 Nov 2024")
    week_range = f"{week_start.strftime('%d %b')} - {week_end.strftime('%d %b %Y')}"
    
    return week_start, week_end, week_range

# --- PDF Generation Functions (Challan) ---

def draw_pdf(pdf_buffer, meta, rows):
    c = canvas.Canvas(pdf_buffer, pagesize=A4)
    pw, ph = A4
    margin = 15 * mm

    c.setFont("Helvetica-Bold", 16)
    title = "NAGPUR BHOPAL TRANSPORT COMPANY"
    title_width = c.stringWidth(title, "Helvetica-Bold", 16)
    c.drawString((pw - title_width) / 2, ph - 35, title)

    c.setFont("Helvetica-Bold", 12)
    route_text = f"{meta['FROM']} TO {meta['TO']} - {meta['month']}"
    route_width = c.stringWidth(route_text, "Helvetica-Bold", 12)
    c.drawString((pw - route_width) / 2, ph - 53, route_text)

    grid_start_y = ph - 80
    grid_width = pw - 2 * margin
    col_width = grid_width / 2
    row_height = 20

    c.setLineWidth(0.5)
    c.rect(margin, grid_start_y - 3*row_height, grid_width, 3*row_height)
    c.line(margin + col_width, grid_start_y - 3*row_height, margin + col_width, grid_start_y)
    c.line(margin, grid_start_y - row_height, margin + grid_width, grid_start_y - row_height)
    c.line(margin, grid_start_y - 2*row_height, margin + grid_width, grid_start_y - 2*row_height)

    c.setFont("Helvetica", 10)
    y_pos = grid_start_y - 14
    c.drawString(margin + 5, y_pos, "Challan No.:")
    c.drawString(margin + 80, y_pos, str(meta['challan_no']))
    c.drawString(margin + col_width + 5, y_pos, "Vehicle No.:")
    c.drawString(margin + col_width + 80, y_pos, str(meta['truck']))

    y_pos -= row_height
    c.drawString(margin + 5, y_pos, "Date:")
    c.drawString(margin + 80, y_pos, str(meta['date']))
    c.drawString(margin + col_width + 5, y_pos, "Broker:")
    c.drawString(margin + col_width + 80, y_pos, "NA")

    y_pos -= row_height
    c.drawString(margin + 5, y_pos, "Driver Name:")
    c.drawString(margin + 80, y_pos, str(meta['driver']))
    c.drawString(margin + col_width + 5, y_pos, "Driver Mob no.:")
    c.drawString(margin + col_width + 85, y_pos, str(meta['driver_mob']))

    table_start_y = grid_start_y - 3*row_height - 25
    table_data = [["Sr.\nNo.", "CONSIGNOR", "CONSIGNEE", "WT. Kgs.", "NO. OF\nPkgs", "FREIGHT", "AMOUNT"]]
    for i, r in enumerate(rows, 1):
        table_data.append([
            str(i), str(r["CONSIGNOR"]), str(r["CONSIGNEE"]),
            str(int(r["WT"])) if r["WT"] else "0",
            str(int(r["PKGS"])) if r["PKGS"] else "0",
            str(round(r["FREIGHT"], 1)) if r["FREIGHT"] else "0",
            str(round(r["AMOUNT"], 1)) if r["AMOUNT"] else "0"
        ])
    table_data.append([
        "TOTAL", "", "", str(int(meta['total_wt'])), str(int(meta['total_pkgs'])),
        "", str(round(meta['total_amount'], 1))
    ])
    col_widths = [35, 90, 90, 55, 60, 55, 65]
    table = Table(table_data, colWidths=col_widths)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472C4')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BACKGROUND', (0, 1), (-1, -2), colors.HexColor('#FFF2CC')),
        ('FONTNAME', (0, 1), (-1, -2), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -2), 9),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#FFD966')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, -1), (-1, -1), 10),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('LINEBELOW', (0, 0), (-1, 0), 2, colors.black),
        ('LINEABOVE', (0, -1), (-1, -1), 2, colors.black),
    ]))
    w, h = table.wrap(0, 0)
    table.drawOn(c, margin, table_start_y - h)

    summary_y = table_start_y - h - 25
    c.setFont("Helvetica", 11)
    c.drawString(margin + 8, summary_y, "GADI BHADAA")
    c.drawRightString(pw - margin - 8, summary_y, str(int(meta['hire'])))
    summary_y -= 18
    c.drawString(margin + 8, summary_y, "LOADING HAMALI")
    c.drawRightString(pw - margin - 8, summary_y, str(int(meta['hamali_loading'])))
    summary_y -= 18
    c.drawString(margin + 8, summary_y, "UNLOADING HAMALI")
    c.drawRightString(pw - margin - 8, summary_y, str(int(meta['hamali_unloading'])))
    summary_y -= 18
    c.drawString(margin + 8, summary_y, "OTHER EXP.")
    c.drawRightString(pw - margin - 8, summary_y, str(int(meta['other_exp'])))
    summary_y -= 20
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin + 8, summary_y, "BALANCE")
    c.drawRightString(pw - margin - 8, summary_y, str(round(meta['balance'], 1)))

    c.showPage()
    c.save()

def draw_summary_pdf(pdf_buffer, route_from, route_to, month_year, summary_rows):
    c = canvas.Canvas(pdf_buffer, pagesize=A4)
    pw, ph = A4
    margin = 15 * mm

    totals = {"qty": 0, "weight": 0, "topay": 0, "hire": 0, "hamali": 0, "balance": 0}
    for row in summary_rows:
        for key in totals:
            totals[key] += float(row[key]) if row[key] else 0

    available_height = ph - 120
    row_height = 20
    rows_per_page = int(available_height / row_height) - 1
    total_data_rows = len(summary_rows)
    num_pages = (total_data_rows + rows_per_page - 1) // rows_per_page

    for page_num in range(num_pages):
        c.setFont("Helvetica-Bold", 18)
        title = f"{route_from} TO {route_to} - {month_year}"
        title_width = c.stringWidth(title, "Helvetica-Bold", 18)
        c.drawString((pw - title_width) / 2, ph - 40, title)
        if num_pages > 1:
            c.setFont("Helvetica", 10)
            page_text = f"Page {page_num + 1} of {num_pages}"
            c.drawString(pw - margin - 80, ph - 40, page_text)

        table_start_y = ph - 80
        table_data = [["Date", "Truck No.", "Chal- No.", "QTY", "Weight", "Topay", "Hire", "Hamali", "Balance - AMT"]]
        start_idx, end_idx = page_num * rows_per_page, min((page_num + 1) * rows_per_page, total_data_rows)
        for row in summary_rows[start_idx:end_idx]:
            table_data.append([
                row["date"], row["truck_no"], row["challan_no"], row["qty"],
                row["weight"], row["topay"], row["hire"], row["hamali"], row["balance"]
            ])
        if page_num == num_pages - 1:
            table_data.append([
                "TOTAL", "", "", str(int(totals["qty"])), str(int(totals["weight"])),
                str(round(totals["topay"], 1)), str(int(totals["hire"])),
                str(int(totals["hamali"])), str(round(totals["balance"], 1))
            ])
        col_widths = [55, 60, 50, 40, 50, 55, 50, 50, 70]
        table = Table(table_data, colWidths=col_widths)
        style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472C4')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#FFF2CC')),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('LINEBELOW', (0, 0), (-1, 0), 2, colors.black)
        ]
        if page_num == num_pages - 1:
            style.extend([
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#FFD966')),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, -1), (-1, -1), 10),
                ('LINEABOVE', (0, -1), (-1, -1), 2, colors.black)
            ])
        table.setStyle(TableStyle(style))
        w, h = table.wrap(0, 0)
        table.drawOn(c, margin, table_start_y - h)
        c.showPage()
    c.save()

# --- Weekly Bill & Ledger PDF Generation ---

def draw_bill_pdf(pdf_buffer, consignor, route, week_range, shipments, summary):

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from reportlab.platypus import Table, TableStyle
    from reportlab.lib import colors

    c = canvas.Canvas(pdf_buffer, pagesize=A4)
    pw, ph = A4
    margin = 15 * mm

    # ============================================================
    #            SINGLE CENTER HEADING  (Your Required Style)
    # ============================================================

    heading_y = ph - 60

    # (ABC TRANSPORT)
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(pw/2, heading_y, f"({consignor})")

    # DELHI TO MUMBAI
    c.setFont("Helvetica-Bold", 16)
    route_heading = route.replace(" → ", " TO ")
    c.drawCentredString(pw/2, heading_y - 22, route_heading.upper())

    # DATE : 20 NOV - 26 NOV 2025
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(pw/2, heading_y - 42, f"DATE : {week_range}")

    # ============================================================
    #                         TABLE
    # ============================================================

    table_start_y = ph - 120

    # REMOVED CONSIGNEE COLUMN
    table_data = [
        ["SR NO", "DATE", "WT (KG)", "FREIGHT (₹/KG)", "PKGS", "AMOUNT (₹)"]
    ]

    total_amount = 0
    total_wt = 0

    # Add shipment rows
    for i, ship in enumerate(shipments, start=1):
        freight_per_kg = ship["amount"] / ship["wt"] if ship["wt"] else 0

        table_data.append([
            str(i),
            ship["date"],
            str(int(ship["wt"])),
            f"{freight_per_kg:.2f}",
            str(int(ship["pkgs"])),
            f"{round(ship['amount'], 2)}"
        ])

        total_amount += ship["amount"]
        total_wt += ship["wt"]

    # SUBTOTAL
    table_data.append([
        "", "SUBTOTAL", str(int(total_wt)), "", "", f"{round(total_amount, 2)}"
    ])

    # OLD BALANCE
    table_data.append([
        "", "OLD BALANCE", "", "", "", f"{round(summary.get('previous_balance', 0), 2)}"
    ])

    # FINAL TOTAL
    final_total = total_amount + summary.get("previous_balance", 0)
    table_data.append([
        "", "FINAL TOTAL", str(int(total_wt)), "", "", f"{round(final_total, 2)}"
    ])

    # Updated column widths (since consignee removed)
    col_widths = [60, 90, 80, 100, 60, 90]

    table = Table(table_data, colWidths=col_widths)

    # ----------------- TABLE STYLE -----------------
    table.setStyle(TableStyle([
        # Header
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#003366')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 10),
        ('ALIGN', (0,0), (-1,0), 'CENTER'),

        # Body
        ('BACKGROUND', (0,1), (-1,-4), colors.HexColor('#F7FBFF')),
        ('FONTNAME', (0,1), (-1,-4), 'Helvetica'),
        ('FONTSIZE', (0,1), (-1,-4), 9),

        # Subtotal
        ('BACKGROUND', (0,-3), (-1,-3), colors.HexColor('#DDEBF7')),
        ('FONTNAME', (0,-3), (-1,-3), 'Helvetica-Bold'),

        # Old Balance
        ('BACKGROUND', (0,-2), (-1,-2), colors.HexColor('#E7E6E6')),
        ('FONTNAME', (0,-2), (-1,-2), 'Helvetica-Bold'),

        # Final Total
        ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor('#003366')),
        ('TEXTCOLOR', (0,-1), (-1,-1), colors.white),
        ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,-1), (-1,-1), 11),

        # Alignment
        ('ALIGN', (0,1), (0,-1), 'CENTER'),
        ('ALIGN', (2,1), (2,-1), 'RIGHT'),
        ('ALIGN', (3,1), (3,-1), 'RIGHT'),
        ('ALIGN', (5,1), (5,-1), 'RIGHT'),

        # Borders
        ('GRID', (0,0), (-1,-1), 0.8, colors.black),
    ]))

    # Draw table
    w, h = table.wrap(0, 0)
    table.drawOn(c, margin, table_start_y - h)

    c.showPage()
    c.save()



def draw_ledger_pdf(pdf_buffer, consignor, route, week_range, shipments, summary):

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from reportlab.platypus import Table, TableStyle
    from reportlab.lib import colors

    c = canvas.Canvas(pdf_buffer, pagesize=A4)
    pw, ph = A4
    margin = 15 * mm

    # HEADER
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(pw/2, ph - 40, "WEEKLY LEDGER")

    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin, ph - 70, f"Consignor :  {consignor}")
    c.drawString(margin, ph - 90, f"Route     :  {route}")
    c.drawString(margin, ph - 110, f"Week      :  {week_range}")

    # ----------------- TABLE -----------------
    table_start_y = ph - 150
    table_data = [["SR\nNO", "CONSIGNEE", "DATE", "WT (KG)", "FREIGHT\n(Rs/KG)", "PKGS", "AMOUNT (Rs)"]]

    total_amount = 0
    total_wt = 0

    for i, ship in enumerate(shipments, start=1):
        freight_per_kg = ship["amount"] / ship["wt"] if ship["wt"] else 0

        table_data.append([
            str(i),
            ship["consignee"][:22],
            ship["date"],
            str(int(ship["wt"])),
            f"{freight_per_kg:.2f}",
            str(int(ship["pkgs"])),
            f"{round(ship['amount'], 2)}"
        ])

        total_amount += ship["amount"]
        total_wt += ship["wt"]

    # SUBTOTAL ONLY
    table_data.append([
        "", "SUBTOTAL", "", str(int(total_wt)), "", "",
        f"{round(total_amount, 2)}"
    ])

    col_widths = [35, 140, 60, 60, 80, 50, 80]

    table = Table(table_data, colWidths=col_widths)

    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#4472C4')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),

        ('BACKGROUND', (0,1), (-1,-2), colors.HexColor('#FFF2CC')),

        ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor('#FFD966')),
        ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),

        ('ALIGN', (0,1), (0,-1), 'CENTER'),
        ('ALIGN', (3,1), (3,-1), 'RIGHT'),
        ('ALIGN', (4,1), (4,-1), 'RIGHT'),
        ('ALIGN', (6,1), (6,-1), 'RIGHT'),

        ('GRID', (0,0), (-1,-1), 0.8, colors.black),
    ]))

    w, h = table.wrap(0, 0)
    table.drawOn(c, margin, table_start_y - h)

    c.showPage()
    c.save()


# --- Main Processing Function (Challans etc.) ---
def process_excel_file(uploaded_file, route_hamali):    
    xls = pd.ExcelFile(uploaded_file)
    df = pd.concat([pd.read_excel(uploaded_file, s, dtype=str) for s in xls.sheet_names], ignore_index=True)
    df["DATE_RAW"] = df["DATE"]
    df.columns = [c.strip() for c in df.columns]
    df["DATE"] = df["DATE"].apply(parse_date_flexible)
    df["FROM"] = df["FROM"].apply(clean_city)
    df["TO"] = df["TO"].apply(clean_city)
    df["CONSIGNOR"] = df["CONSIGNOR"].apply(clean_consignor)
    df["NAME OF THE DRIVER"] = df["NAME OF THE DRIVER"].apply(clean_driver)
    df["WT"] = df["WT. Kgs."].apply(clean_num)
    df["PKGS"] = df["NO. OF Pkgs"].apply(clean_num)
    df["FREIGHT"] = df["FREIGHT"].apply(clean_num)
    df["AMOUNT"] = df["AMOUNT"].apply(clean_num)
    df["Hire"] = df["Hire"].apply(clean_num)
    
    groups = df.groupby([df["S. NO."], df["DATE"], df["NAME OF THE DRIVER"], df["FROM"], df["TO"]])
    month_wise_data = {}
    route_summaries = {}
    challan_counter = 0
    progress_bar = st.progress(0)
    status_text = st.empty()
    total_groups = len(groups)
    
    for idx, ((serial_no, date, driver, FROM, TO), grp) in enumerate(groups):
        challan_counter += 1
        progress_bar.progress((idx + 1) / total_groups)
        status_text.text(f"Processing challan {challan_counter}/{total_groups}...")
        rows = []
        for _, r in grp.iterrows():
            rows.append({
                "CONSIGNOR": r["CONSIGNOR"],
                "CONSIGNEE": r["CONSIGNEE"],
                "WT": r["WT"],
                "PKGS": r["PKGS"],
                "FREIGHT": r["FREIGHT"],
                "AMOUNT": r["AMOUNT"]
            })
        total_wt = grp["WT"].sum()
        total_pkgs = grp["PKGS"].sum()
        total_amount = grp["AMOUNT"].sum()
        hire = grp["Hire"].iloc[0]
        
        route_key = f"{FROM}_TO_{TO}"
        hamali_loading = route_hamali.get(route_key, {}).get("loading", 0)
        hamali_unloading = route_hamali.get(route_key, {}).get("unloading", 0)
        hamali_total = hamali_loading + hamali_unloading
        other_exp = 0
        balance = total_amount - hire - hamali_total - other_exp

        meta = {
            "FROM": FROM,
            "TO": TO,
            "month": date.strftime("%B").upper() if not pd.isna(date) else "",
            "driver": driver,
            "driver_mob": grp["DRIVER MOB. NO."].iloc[0] if "DRIVER MOB. NO." in grp.columns else "NA",
            "truck": grp["TRUCK NO."].iloc[0] if "TRUCK NO." in grp.columns else "NA",
            "challan_no": str(serial_no),
            "date": date.strftime("%d/%m/%Y") if not pd.isna(date) else "",
            "total_wt": total_wt,
            "total_pkgs": total_pkgs,
            "total_amount": total_amount,
            "hire": hire,
            "hamali_loading": hamali_loading,
            "hamali_unloading": hamali_unloading,
            "other_exp": other_exp,
            "balance": balance,
        }

        pdf_buffer = io.BytesIO()
        draw_pdf(pdf_buffer, meta, rows)
        pdf_buffer.seek(0)
        safe_serial = str(serial_no).replace("/", "-").replace("\\", "-").replace(" ", "_")
        fname = f"{date.strftime('%Y%m%d')}__{safe_serial}__{driver.replace(' ','_')}__{FROM}_to_{TO}.pdf"
        month_key = date.strftime("%B_%Y") if not pd.isna(date) else "Unknown_Month"
        if month_key not in month_wise_data: month_wise_data[month_key] = {}
        if route_key not in month_wise_data[month_key]: month_wise_data[month_key][route_key] = []
        month_wise_data[month_key][route_key].append((fname, pdf_buffer.getvalue()))
        
        summary_key = (month_key, FROM, TO)
        if summary_key not in route_summaries: route_summaries[summary_key] = []
        route_summaries[summary_key].append({
            "date": date.strftime("%d/%m/%Y") if not pd.isna(date) else "",
            "truck_no": meta["truck"],
            "challan_no": str(serial_no),
            "qty": str(int(total_pkgs)),
            "weight": str(int(total_wt)),
            "topay": str(round(total_amount, 1)),
            "hire": str(int(hire)),
            "hamali": str(int(hamali_total)),
            "balance": str(round(balance, 1))
        })
    
    status_text.text("Generating summary reports...")
    for (month_key, route_from, route_to), summary_rows in route_summaries.items():
        summary_rows.sort(key=lambda x: x["date"])
        pdf_buffer = io.BytesIO()
        month_display = month_key.replace("_", " ")
        draw_summary_pdf(pdf_buffer, route_from, route_to, month_display.upper(), summary_rows)
        pdf_buffer.seek(0)
        route_key = f"{route_from}_TO_{route_to}"
        fname = f"SUMMARY__{route_from}_TO_{route_to}__{month_key}.pdf"
        if month_key not in month_wise_data: month_wise_data[month_key] = {}
        if route_key not in month_wise_data[month_key]: month_wise_data[month_key][route_key] = []
        month_wise_data[month_key][route_key].append((fname, pdf_buffer.getvalue()))
    
    progress_bar.progress(1.0)
    status_text.text("✅ Processing complete!")
    return month_wise_data, challan_counter, len(route_summaries)

# --- Ledger Processing Function ---
def generate_weekly_ledgers(uploaded_file, consignor_old_balances):
    xls = pd.ExcelFile(uploaded_file)
    df = pd.concat([pd.read_excel(uploaded_file, s, dtype=str) for s in xls.sheet_names], ignore_index=True)
    
    df.columns = [c.strip() for c in df.columns]
    df["DATE"] = df["DATE"].apply(parse_date_flexible)
    df["FROM"] = df["FROM"].apply(clean_city)
    df["TO"] = df["TO"].apply(clean_city)
    df["CONSIGNOR"] = df["CONSIGNOR"].apply(clean_consignor)
    df["CONSIGNEE"] = df["CONSIGNEE"].apply(clean_consignor)
    df["WT"] = df["WT. Kgs."].apply(clean_num)
    df["PKGS"] = df["NO. OF Pkgs"].apply(clean_num)
    df["AMOUNT"] = df["AMOUNT"].apply(clean_num)
    df["Hire"] = df["Hire"].apply(clean_num)
    
    # Filter valid dates and routes
    df = df[df["DATE"].notna() & (df["FROM"] != "") & (df["TO"] != "")].copy()
    
    # Add week information (Monday to Sunday)
    df["WEEK_START"] = df["DATE"].apply(lambda x: get_week_info(x)[0])
    df["WEEK_END"] = df["DATE"].apply(lambda x: get_week_info(x)[1])
    df["WEEK_RANGE"] = df["DATE"].apply(lambda x: get_week_info(x)[2])
    df["ROUTE"] = df["FROM"] + " → " + df["TO"]
    
    # Group by consignor, week, route
    ledger_data = {}
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    groups = df.groupby(["CONSIGNOR", "WEEK_START", "WEEK_END", "WEEK_RANGE", "ROUTE", "FROM", "TO"])
    total_groups = len(groups)
    
    for idx, ((consignor, week_start, week_end, week_range, route, from_city, to_city), grp) in enumerate(groups):
        progress_bar.progress((idx + 1) / total_groups)
        status_text.text(f"Generating ledger {idx + 1}/{total_groups}...")
        
        # Use the manual old balance for this specific consignor
        previous_balance = consignor_old_balances.get(consignor, 0)
        
        # Prepare shipment details
        shipments = []
        for _, row in grp.iterrows():
            shipments.append({
                "date": row["DATE"].strftime("%d/%m/%Y"),
                "consignee": row["CONSIGNEE"],
                "wt": row["WT"],
                "pkgs": row["PKGS"],
                "amount": row["AMOUNT"]
            })
        
        # Calculate summary
        total_trips = len(grp)
        total_wt = grp["WT"].sum()
        total_pkgs = grp["PKGS"].sum()
        total_amount = grp["AMOUNT"].sum()
        total_hire = grp["Hire"].sum()
        net_amount = total_amount - total_hire
        final_balance = net_amount + previous_balance
        
        summary = {
            "total_trips": total_trips,
            "total_wt": total_wt,
            "total_pkgs": total_pkgs,
            "total_amount": total_amount,
            "total_hire": total_hire,
            "net_amount": net_amount,
            "previous_balance": previous_balance,
            "final_balance": final_balance
        }
        
        # Generate BILL PDF
        bill_buffer = io.BytesIO()
        draw_bill_pdf(bill_buffer, consignor, route, week_range, shipments, summary)
        bill_buffer.seek(0)

        # Generate LEDGER PDF (no old balance)
        ledger_buffer = io.BytesIO()
        draw_ledger_pdf(ledger_buffer, consignor, route, week_range, shipments, summary)
        ledger_buffer.seek(0)
        
        # Generate Excel
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            # Shipments sheet
            shipments_df = pd.DataFrame(shipments)
            shipments_df.to_excel(writer, sheet_name='Shipments', index=False)
            
            # Summary sheet
            summary_df = pd.DataFrame([{
                "Week Range": week_range,
                "Consignor": consignor,
                "Route": route,
                "Total Trips": total_trips,
                "Total Weight (KG)": total_wt,
                "Total Packages": total_pkgs,
                "Total Amount (₹)": total_amount,
                "Total Hire (₹)": total_hire,
                "Net Amount (₹)": net_amount,
                "Previous Outstanding (₹)": previous_balance,
                "Final Balance (₹)": final_balance
            }])
            summary_df.to_excel(writer, sheet_name='Summary', index=False)
        excel_buffer.seek(0)
        
        # Organize by consignor > week (using week_start as key for chronological sorting)
        if consignor not in ledger_data:
            ledger_data[consignor] = {}
        
        week_key = week_start.strftime('%Y-%m-%d')  # Use date as key for proper sorting
        if week_key not in ledger_data[consignor]:
            ledger_data[consignor][week_key] = {}
        
        route_safe = route.replace(' → ', '_to_')
        ledger_data[consignor][week_key][route_safe] = {
            "bill_pdf": (
                f"{consignor}__{week_range.replace(' - ', '_to_').replace(' ', '_')}__{route_safe}__BILL.pdf",
                bill_buffer.getvalue()
            ),
            "ledger_pdf": (
                f"{consignor}__{week_range.replace(' - ', '_to_').replace(' ', '_')}__{route_safe}__LEDGER.pdf",
                ledger_buffer.getvalue()
            ),
            "excel": (
                f"{consignor}__{week_range.replace(' - ', '_to_').replace(' ', '_')}__{route_safe}.xlsx",
                excel_buffer.getvalue()
            ),
            "summary": summary,
            "week_start": week_start,
            "week_end": week_end,
            "route": route,
            "week_range": week_range
        }
    
    progress_bar.progress(1.0)
    status_text.text("✅ Ledger generation complete!")
    
    return ledger_data

# --- Main App ---
def main():
    st.set_page_config(
        page_title="Transport Challan & Ledger Generator Pro",
        page_icon="🚚",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    st.markdown("""
    <div class="main-header">
        <h1>🚚 Transport Challan & Ledger Generator Pro</h1>
        <p style="font-size: 1.2rem;">Professional PDF Challans, Reports & Weekly Ledgers</p>
    </div>
    """, unsafe_allow_html=True)
    
    with st.sidebar:
        st.image("https://img.icons8.com/clouds/200/000000/truck.png", width=150)
        st.title("📋 Features")
        st.markdown("""
        ✅ **Multi-sheet Excel support**  
        ✅ **Auto route detection**  
        ✅ **Professional PDF design**  
        ✅ **Summary reports**  
        ✅ **Weekly ledgers (Mon-Sun)**  
        ✅ **Individual consignor balances**  
        ✅ **Bulk download (ZIP)**  
        ✅ **Smart date parsing**  
        """)
        st.divider()
        st.markdown("### 💡 Quick Tips")
        st.info("Upload Excel with columns: S. NO., DATE, FROM, TO, CONSIGNOR, CONSIGNEE, etc.")
        st.divider()
        st.markdown("### 📞 Support")
        st.markdown("Need help? Contact us!")
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🚀 Generate Challans",
        "📊 Generate Ledgers",
        "📖 How It Works",
        "💼 Pricing",
        "📑 All Party Summary"
    ])

    
    # ---------------- TAB 1: CHALLANS ----------------
    with tab1:
        col1, col2 = st.columns([2, 1])
        with col1:
            st.markdown("### 📤 Upload Your Excel File")
            uploaded_file = st.file_uploader(
                "Choose your transport data file",
                type=['xlsx', 'xls'],
                help="Upload Excel with transport data",
                key="challan_upload"
            )
        with col2:
            st.markdown("### ⚙️ Settings")
            other_exp = st.number_input("Other Expenses", value=0, step=100)
        
        route_hamali = None
        if uploaded_file:
            xls = pd.ExcelFile(uploaded_file)
            df = pd.concat([pd.read_excel(uploaded_file, s, dtype=str) for s in xls.sheet_names], ignore_index=True)
            df["FROM"] = df["FROM"].apply(clean_city)
            df["TO"] = df["TO"].apply(clean_city)
            routes = sorted({(row["FROM"], row["TO"]) for _, row in df.iterrows() if row["FROM"] and row["TO"]})

            st.markdown("### 🛣️ Set Hamali For Each Route (Loading/Unloading)")
            route_hamali = {}
            for route_from, route_to in routes:
                colA, colB, colC = st.columns([3, 2, 2])
                route_key = f"{route_from}_TO_{route_to}"
                with colA:
                    st.markdown(f"**{route_from} → {route_to}**")
                with colB:
                    hamali_loading = st.number_input(
                        f"Loading Hamali ({route_from} → {route_to})", min_value=0, max_value=50000,
                        value=1700, key=f"hamali_load_{route_key}")
                with colC:
                    hamali_unloading = st.number_input(
                        f"Unloading Hamali ({route_from} → {route_to})", min_value=0, max_value=50000,
                        value=1700, key=f"hamali_unload_{route_key}")
                route_hamali[route_key] = {"loading": hamali_loading, "unloading": hamali_unloading}
        
        if uploaded_file and route_hamali and st.button(
            "🎯 Generate Challans & Reports", type="primary", use_container_width=True):
            with st.spinner("Processing your file..."):
                try:
                    month_wise_data, challan_count, summary_count = process_excel_file(uploaded_file, route_hamali)
                    st.markdown(f"""
                    <div class="success-message">
                        <h3>✅ Success! Generated {challan_count} Challans & {summary_count} Summary Reports</h3>
                        <p>Organized by {len(month_wise_data)} month(s)</p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.markdown(f"""
                        <div class="stats-box">
                            <h2>{challan_count}</h2>
                            <p>Challans Generated</p>
                        </div>
                        """, unsafe_allow_html=True)
                    with col2:
                        st.markdown(f"""
                        <div class="stats-box">
                            <h2>{len(month_wise_data)}</h2>
                            <p>Months Processed</p>
                        </div>
                        """, unsafe_allow_html=True)
                    with col3:
                        total_routes = sum(len(routes) for routes in month_wise_data.values())
                        st.markdown(f"""
                        <div class="stats-box">
                            <h2>{total_routes}</h2>
                            <p>Route-Month Combinations</p>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    st.markdown("---")
                    st.markdown("### 📥 Download Your Files")
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                        for month_key, routes in month_wise_data.items():
                            for route_key, files in routes.items():
                                for fname, pdf_data in files:
                                    zip_file.writestr(f"{month_key}/{route_key}/{fname}", pdf_data)
                    zip_buffer.seek(0)
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.download_button(
                            label="📦 Download All (ZIP) - Month-wise Organized",
                            data=zip_buffer,
                            file_name=f"Transport_Challans_MonthWise_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                            mime="application/zip",
                            use_container_width=True
                        )
                    
                    st.markdown("---")
                    st.markdown("### 📅 Month-wise Organization")
                    sorted_months = sorted(month_wise_data.keys(), 
                                         key=lambda x: datetime.strptime(x, "%B_%Y") if x != "Unknown_Month" else datetime.min)
                    
                    for month_key in sorted_months:
                        routes = month_wise_data[month_key]
                        month_display = month_key.replace("_", " ")
                        with st.expander(f"📅 **{month_display}** - {len(routes)} Routes", expanded=True):
                            month_total_files = sum(len(files) for files in routes.values())
                            st.info(f"📊 **Total Files:** {month_total_files} (Challans + Summary Reports)")
                            
                            month_zip = io.BytesIO()
                            with zipfile.ZipFile(month_zip, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                                for route_key, files in routes.items():
                                    for fname, pdf_data in files:
                                        zip_file.writestr(f"{route_key}/{fname}", pdf_data)
                            month_zip.seek(0)
                            
                            st.download_button(
                                label=f"📥 Download {month_display} (All Routes)",
                                data=month_zip,
                                file_name=f"{month_key}_All_Routes.zip",
                                mime="application/zip",
                                key=f"month_{month_key}"
                            )
                            
                            st.markdown("---")
                            for route_key, files in routes.items():
                                route_display = route_key.replace("_TO_", " → ")
                                col1, col2 = st.columns([3, 1])
                                with col1:
                                    st.markdown(f"#### 🛣️ {route_display}")
                                    st.caption(f"{len(files)} files (Challans + Summary)")
                                with col2:
                                    route_zip = io.BytesIO()
                                    with zipfile.ZipFile(route_zip, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                                        for fname, pdf_data in files:
                                            zip_file.writestr(fname, pdf_data)
                                    route_zip.seek(0)
                                    st.download_button(
                                        label="📥 Download",
                                        data=route_zip,
                                        file_name=f"{month_key}_{route_key}.zip",
                                        mime="application/zip",
                                        key=f"{month_key}_{route_key}",
                                        use_container_width=True
                                    )
                                
                                with st.container():
                                    for i, (fname, pdf_data) in enumerate(files[:5]):
                                        file_icon = "📊" if "SUMMARY" in fname else "📄"
                                        col1, col2 = st.columns([4, 1])
                                        with col1:
                                            st.text(f"{file_icon} {fname}")
                                        with col2:
                                            st.download_button(
                                                "⬇️",
                                                data=pdf_data,
                                                file_name=fname,
                                                mime="application/pdf",
                                                key=f"{month_key}_{route_key}_{i}"
                                            )
                                    if len(files) > 5:
                                        st.caption(f"+ {len(files) - 5} more files...")
                                st.markdown("---")
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
                    st.exception(e)
    
    # ---------------- TAB 2: WEEKLY LEDGERS ----------------
    with tab2:
        st.markdown("### 📊 Generate Consignor-wise Weekly Ledgers")
        st.info("Upload your Excel file to generate weekly ledgers (Monday-Sunday) for each consignor with individual old balance settings")
        
        uploaded_ledger_file = st.file_uploader(
            "Choose your transport data file for ledger generation",
            type=['xlsx', 'xls'],
            help="Upload Excel with transport data",
            key="ledger_upload"
        )
        
        consignor_old_balances = {}
        
        if uploaded_ledger_file:
            # Read file to get list of consignors
            xls = pd.ExcelFile(uploaded_ledger_file)
            df_preview = pd.concat([pd.read_excel(uploaded_ledger_file, s, dtype=str) for s in xls.sheet_names], ignore_index=True)
            df_preview.columns = [c.strip() for c in df_preview.columns]
            df_preview["CONSIGNOR"] = df_preview["CONSIGNOR"].apply(clean_consignor)
            
            # Get unique consignors
            consignors = sorted([c for c in df_preview["CONSIGNOR"].unique() if c and c != ""])
            
            st.markdown("### 💰 Set Old Balance for Each Consignor")
            st.markdown("*Enter the previous outstanding balance for each consignor*")
            
            # Create input fields for each consignor
            cols_per_row = 2
            for i in range(0, len(consignors), cols_per_row):
                cols = st.columns(cols_per_row)
                for j, col in enumerate(cols):
                    if i + j < len(consignors):
                        consignor = consignors[i + j]
                        with col:
                            old_balance = st.number_input(
                                f"**{consignor}**",
                                value=0.0,
                                step=100.0,
                                format="%.2f",
                                key=f"balance_{consignor}"
                            )
                            consignor_old_balances[consignor] = old_balance
            
            st.markdown("---")
        
        if uploaded_ledger_file and st.button(
            "📊 Generate Weekly Ledgers", type="primary", use_container_width=True):
            with st.spinner("Generating weekly ledgers..."):
                try:
                    ledger_data = generate_weekly_ledgers(uploaded_ledger_file, consignor_old_balances)
                    
                    total_ledgers = sum(len(routes) for consignor in ledger_data.values() for routes in consignor.values())
                    
                    st.markdown(f"""
                    <div class="success-message">
                        <h3>✅ Success! Generated {total_ledgers} Weekly Ledgers</h3>
                        <p>For {len(ledger_data)} consignor(s)</p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"""
                        <div class="stats-box">
                            <h2>{len(ledger_data)}</h2>
                            <p>Consignors</p>
                        </div>
                        """, unsafe_allow_html=True)
                    with col2:
                        st.markdown(f"""
                        <div class="stats-box">
                            <h2>{total_ledgers}</h2>
                            <p>Weekly Ledgers (Bill + Ledger)</p>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    st.markdown("---")
                    st.markdown("### 📥 Download Ledgers")
                    
                    # Create master ZIP with all ledgers
                    master_zip = io.BytesIO()
                    with zipfile.ZipFile(master_zip, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                        for consignor, weeks_data in ledger_data.items():
                            for week_key, routes in weeks_data.items():
                                for route_key, data in routes.items():
                                    bill_name, bill_pdf = data["bill_pdf"]
                                    ledger_name, ledger_pdf = data["ledger_pdf"]
                                    excel_name, excel_content = data["excel"]
                                    folder = f"{consignor}/{data['week_range']}"
                                    zip_file.writestr(f"{folder}/{bill_name}", bill_pdf)
                                    zip_file.writestr(f"{folder}/{ledger_name}", ledger_pdf)
                                    zip_file.writestr(f"{folder}/{excel_name}", excel_content)
                    master_zip.seek(0)
                    
                    st.download_button(
                        label="📦 Download All Ledgers (ZIP)",
                        data=master_zip,
                        file_name=f"Weekly_Ledgers_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                        mime="application/zip",
                        use_container_width=True
                    )
                    
                    st.markdown("---")
                    st.markdown("### 👤 Consignor-wise Ledgers")
                    
                    for consignor in sorted(ledger_data.keys()):
                        weeks_data = ledger_data[consignor]
                        total_consignor_ledgers = sum(len(routes) for routes in weeks_data.values())
                        
                        with st.expander(f"👤 **{consignor}** - {total_consignor_ledgers} Week(s)", expanded=True):
                            # Create consignor ZIP
                            consignor_zip = io.BytesIO()
                            with zipfile.ZipFile(consignor_zip, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                                for week_key, routes in weeks_data.items():
                                    for route_key, data in routes.items():
                                        bill_name, bill_pdf = data["bill_pdf"]
                                        ledger_name, ledger_pdf = data["ledger_pdf"]
                                        excel_name, excel_content = data["excel"]
                                        folder = f"{data['week_range']}"
                                        zip_file.writestr(f"{folder}/{bill_name}", bill_pdf)
                                        zip_file.writestr(f"{folder}/{ledger_name}", ledger_pdf)
                                        zip_file.writestr(f"{folder}/{excel_name}", excel_content)
                            consignor_zip.seek(0)
                            
                            st.download_button(
                                label=f"📥 Download All for {consignor}",
                                data=consignor_zip,
                                file_name=f"{consignor.replace(' ', '_')}_Ledgers.zip",
                                mime="application/zip",
                                key=f"consignor_{consignor}"
                            )
                            
                            st.markdown("---")
                            
                            # Sort weeks chronologically
                            sorted_weeks = sorted(weeks_data.keys())
                            
                            for week_key in sorted_weeks:
                                routes = weeks_data[week_key]
                                
                                # Get week range from first route's data
                                first_route_data = next(iter(routes.values()))
                                week_range = first_route_data['week_range']
                                
                                st.markdown(f"#### 📅 {week_range}")
                                
                                for route_key, week_data in routes.items():
                                    col1, col2, col3 = st.columns([2, 2, 2])
                                    
                                    with col1:
                                        st.markdown(f"**{week_data['route']}**")
                                    
                                    with col2:
                                        summary = week_data["summary"]
                                        st.caption(
                                            f"Trips: {summary['total_trips']} | "
                                            f"Weight: {summary['total_wt']:.0f} kg | "
                                            f"Final Balance (Bill): ₹{summary['final_balance']:.2f}"
                                        )
                                    
                                    with col3:
                                        bill_name, bill_pdf = week_data["bill_pdf"]
                                        ledger_name, ledger_pdf = week_data["ledger_pdf"]
                                        excel_name, excel_content = week_data["excel"]
                                        
                                        st.download_button(
                                            "🧾 Bill PDF",
                                            data=bill_pdf,
                                            file_name=bill_name,
                                            mime="application/pdf",
                                            key=f"bill_{consignor}_{week_key}_{route_key}"
                                        )
                                        st.download_button(
                                            "📘 Ledger PDF",
                                            data=ledger_pdf,
                                            file_name=ledger_name,
                                            mime="application/pdf",
                                            key=f"ledger_{consignor}_{week_key}_{route_key}"
                                        )
                                        st.download_button(
                                            "📊 Excel",
                                            data=excel_content,
                                            file_name=excel_name,
                                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                            key=f"excel_{consignor}_{week_key}_{route_key}"
                                        )
                                
                                st.markdown("---")
                
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
                    st.exception(e)
    
    # ---------------- TAB 3: HOW IT WORKS ----------------
    with tab3:
        st.markdown("""
        ## 📖 How It Works

        ### Challan Generation (Tab 1)
        
        **Step 1: Prepare Your Excel**
        Your Excel file should contain these columns:
        - **S. NO.** - Serial number (unique per challan)
        - **DATE** - Date (DD/MM/YYYY format)
        - **FROM** - Origin city
        - **TO** - Destination city
        - **TRUCK NO.** - Vehicle number
        - **NAME OF THE DRIVER** - Driver name
        - **DRIVER MOB. NO.** - Driver mobile
        - **CONSIGNOR** - Sender details
        - **CONSIGNEE** - Receiver details
        - **WT. Kgs.** - Weight in kg
        - **NO. OF Pkgs** - Package count
        - **FREIGHT** - Freight charges
        - **AMOUNT** - Total amount
        - **Hire** - Vehicle hire charges

        **Step 2: Upload & Process**
        Upload your Excel file, set hamali charges for each route, and generate challans automatically.

        ---

        ### Weekly Ledger Generation (Tab 2)
        
        **Features:**
        - Automatically groups shipments by consignor, actual calendar weeks (Monday-Sunday), and route
        - Uses proper week boundaries regardless of month
        - Standardizes routes (Mumbai/Delhi only)
        - Individual old balance input for each consignor
        - Generates both **Bill PDF** and **Ledger PDF** + Excel
        
        **Week Definition:**
        - Each week runs from Monday to Sunday
        - Week range displayed as "DD MMM - DD MMM YYYY" (e.g., "20 Nov - 26 Nov 2024")
        - Old balance must be entered manually for each consignor
        
        **Balance Logic (Bill):**
        ```
        Net Amount = Total Amount - Total Hire
        Final Balance = Net Amount + Old Balance (per consignor)
        ```
        
        **Important:**
        - **Bill PDF** = Shows Subtotal + Old Balance + Final Total  
        - **Ledger PDF** = Shows only weekly Subtotal (no old balance)  
        
        **Output Structure:**
        - Organized by Consignor → Week (Monday-Sunday) → Route
        - Bill PDF: Weekly statement with outstanding balance
        - Ledger PDF: Clean weekly ledger without previous balance
        - Excel: Detailed data for further analysis
        """)
        
        st.image("https://img.icons8.com/clouds/300/000000/process.png", width=200)
    
    # ---------------- TAB 4: PRICING (Demo) ----------------
    with tab4:
        st.markdown("## 💼 Pricing Plans")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("""
            <div class="feature-box">
                <h3>🆓 Basic</h3>
                <h2>₹999/month</h2>
                <ul>
                    <li>100 challans/month</li>
                    <li>Basic templates</li>
                    <li>Email support</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)
        with col2:
            st.markdown("""
            <div class="feature-box" style="border-left-color: #28a745;">
                <h3>⭐ Pro</h3>
                <h2>₹2,499/month</h2>
                <ul>
                    <li>500 challans/month</li>
                    <li>Custom templates</li>
                    <li>Priority support</li>
                    <li>Weekly ledgers</li>
                    <li>API access</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)
        with col3:
            st.markdown("""
            <div class="feature-box" style="border-left-color: #dc3545;">
                <h3>🚀 Enterprise</h3>
                <h2>Custom</h2>
                <ul>
                    <li>Unlimited challans</li>
                    <li>White-label solution</li>
                    <li>Dedicated support</li>
                    <li>Custom integrations</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)
        st.markdown("---")
        st.markdown("### 🎁 Special Offer")
        st.success("Get 20% off on annual plans! Use code: TRANSPORT2024")

    


    # ---------------- TAB 5: ALL PARTY SUMMARY ----------------
    with tab5:

        st.markdown("## 📑 All Party Summary Report")
        st.info("Upload Excel file to generate Party-wise summary like the PDF you uploaded (Sum of WT, Freight, Amount).")

        uploaded_summary = st.file_uploader(
            "Upload Excel for Summary Report",
            type=['xlsx', 'xls'],
            key="summary_upload"
        )

        if uploaded_summary:
            st.markdown("### ⚙️ Optional Filters")

            # Load data
            xls = pd.ExcelFile(uploaded_summary)
            df_sum = pd.concat([pd.read_excel(uploaded_summary, s, dtype=str) for s in xls.sheet_names],
                            ignore_index=True)

            # Clean columns
            df_sum.columns = [c.strip() for c in df_sum.columns]
            df_sum["CONSIGNOR"] = df_sum["CONSIGNOR"].apply(clean_consignor)
            df_sum["WT"] = df_sum["WT. Kgs."].apply(clean_num)
            df_sum["AMOUNT"] = df_sum["AMOUNT"].apply(clean_num)
            df_sum["FREIGHT"] = df_sum["FREIGHT"].apply(clean_num)

            # Drop empty consignors
            df_sum = df_sum[df_sum["CONSIGNOR"] != ""]

            # Group summary
            summary_df = df_sum.groupby("CONSIGNOR").agg(
                SUM_WT=("WT", "sum"),
                FREIGHT=("FREIGHT", "max"),
                SUM_AMOUNT=("AMOUNT", "sum")
            ).reset_index()

            # Grand total row
            grand_row = pd.DataFrame({
                "CONSIGNOR": ["Grand Total"],
                "SUM_WT": [summary_df["SUM_WT"].sum()],
                "FREIGHT": [""],
                "SUM_AMOUNT": [summary_df["SUM_AMOUNT"].sum()]
            })

            summary_df_display = pd.concat([summary_df, grand_row], ignore_index=True)

            st.markdown("### 📋 Summary Table")
            st.dataframe(summary_df_display, use_container_width=True)

            # ===================== PDF GENERATION =====================
            def generate_summary_pdf(summary_df):
                buffer = io.BytesIO()
                c = canvas.Canvas(buffer, pagesize=A4)

                pw, ph = A4
                margin = 20
                y = ph - 40

                c.setFont("Helvetica-Bold", 16)
                c.drawString(margin, y, "ALL PARTY SUMMARY REPORT")
                y -= 40

                table_data = [["PARTY NAME", "SUM WT (KGS)", "FREIGHT", "SUM AMOUNT (Rs)"]]

                # Add rows
                for _, row in summary_df.iterrows():
                    table_data.append([
                        row["CONSIGNOR"],
                        str(int(row["SUM_WT"])) if pd.notna(row["SUM_WT"]) else "",
                        str(row["FREIGHT"]) if pd.notna(row["FREIGHT"]) else "",
                        str(round(row["SUM_AMOUNT"], 2)) if pd.notna(row["SUM_AMOUNT"]) else ""
                    ])

                col_widths = [170, 90, 70, 110]
                table = Table(table_data, colWidths=col_widths)

                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472C4')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                    ('GRID', (0, 0), (-1, -1), 0.8, colors.black),
                    ('FONTNAME', (0, 1), (-1, -2), 'Helvetica'),
                    ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#FFD966')),
                    ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold')
                ]))

                w, h = table.wrap(0, 0)
                table.drawOn(c, margin, y - h)

                c.showPage()
                c.save()
                buffer.seek(0)
                return buffer

            # Download PDF
            pdf_buffer = generate_summary_pdf(summary_df_display)

            st.download_button(
                "📄 Download Summary PDF",
                data=pdf_buffer,
                file_name="All_Party_Summary.pdf",
                mime="application/pdf",
                use_container_width=True
            )

            # Download Excel
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                summary_df_display.to_excel(writer, index=False)
            excel_buffer.seek(0)

            st.download_button(
                "📊 Download Summary Excel",
                data=excel_buffer,
                file_name="All_Party_Summary.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )


if __name__ == "__main__":
    main()
