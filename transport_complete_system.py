import streamlit as st
import pandas as pd
import io
import zipfile
from datetime import datetime, timedelta
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Table, TableStyle
from reportlab.lib import colors

# --- Custom CSS ---
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
    .ledger-card {
        padding: 1.5rem;
        background: white;
        border: 2px solid #667eea;
        border-radius: 10px;
        margin: 1rem 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
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
    if "BOMBAY" in x or "MUMBAI" in x: return "MUMBAI"
    if "DELHI" in x: return "DELHI"
    return " ".join(x.split())

def clean_driver(x):
    if not isinstance(x, str): return "NA"
    x = x.upper().strip()
    if x in ["", "NA", "N/A", "NONE", "-", "--"]: return "NA"
    return " ".join(x.split())

def clean_num(x):
    try:
        val = float(str(x).strip())
        return val if not pd.isna(val) else 0
    except: return 0

def get_week_range(date):
    """Get week number and date range for a given date"""
    day = date.day
    if day <= 7: return 1, f"01-07 {date.strftime('%B %Y')}"
    elif day <= 14: return 2, f"08-14 {date.strftime('%B %Y')}"
    elif day <= 21: return 3, f"15-21 {date.strftime('%B %Y')}"
    else: return 4, f"22-{date.strftime('%d')} {date.strftime('%B %Y')}"

def get_route_charges(from_city, to_city):
    """Get loading and unloading charges based on route"""
    if from_city == "DELHI" and to_city == "MUMBAI":
        return 1700, 1600  # Loading, Unloading
    elif from_city == "MUMBAI" and to_city == "DELHI":
        return 2200, 2200
    else:
        return 1700, 1700  # Default

# --- PDF Generation for Challans (Original) ---
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

# --- NEW: Weekly Ledger PDF Generation ---
def draw_ledger_pdf(pdf_buffer, ledger_data):
    c = canvas.Canvas(pdf_buffer, pagesize=A4)
    pw, ph = A4
    margin = 15 * mm
    
    # Header
    c.setFont("Helvetica-Bold", 18)
    title = "WEEKLY CONSIGNOR LEDGER"
    title_width = c.stringWidth(title, "Helvetica-Bold", 18)
    c.drawString((pw - title_width) / 2, ph - 30, title)
    
    c.setFont("Helvetica-Bold", 14)
    c.drawString(margin, ph - 55, f"WEEK: {ledger_data['week_range']}")
    c.drawString(margin, ph - 75, f"CONSIGNOR: {ledger_data['consignor']}")
    c.drawString(margin, ph - 95, f"ROUTE: {ledger_data['route']}")
    
    # Transaction Table
    table_start_y = ph - 120
    table_data = [["DATE", "CONSIGNEE", "WT (KG)", "PKGS", "AMOUNT (₹)"]]
    
    for entry in ledger_data['entries']:
        table_data.append([
            entry['date'],
            entry['consignee'],
            str(int(entry['wt'])),
            str(int(entry['pkgs'])),
            f"₹{entry['amount']:,.0f}"
        ])
    
    col_widths = [70, 140, 80, 60, 90]
    table = Table(table_data, colWidths=col_widths)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472C4')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#FFF2CC')),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    
    w, h = table.wrap(0, 0)
    table.drawOn(c, margin, table_start_y - h)
    
    # Summary Section
    summary_y = table_start_y - h - 30
    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin, summary_y, "SUMMARY")
    
    summary_y -= 25
    c.setFont("Helvetica", 10)
    summary_items = [
        ("TOTAL WEIGHT:", f"{ledger_data['total_wt']:,.0f} KG"),
        ("TOTAL PACKAGES:", f"{ledger_data['total_pkgs']:,}"),
        ("TOTAL TRIPS:", f"{ledger_data['total_trips']}"),
        ("TOTAL AMOUNT:", f"₹{ledger_data['total_amount']:,.2f}"),
        ("", ""),
        ("LOADING CHARGE:", f"₹{ledger_data['loading_charge']:,.0f}"),
        ("UNLOADING CHARGE:", f"₹{ledger_data['unloading_charge']:,.0f}"),
        ("HIRE:", f"₹{ledger_data['hire']:,.0f}"),
        ("", ""),
        ("PREVIOUS BALANCE:", f"₹{ledger_data['previous_balance']:,.2f}"),
        ("MANUAL DEDUCTION:", f"₹{ledger_data['manual_deduction']:,.2f}"),
        ("MANUAL ADDITION:", f"₹{ledger_data['manual_addition']:,.2f}"),
    ]
    
    for label, value in summary_items:
        if label:
            c.drawString(margin + 10, summary_y, label)
            c.drawRightString(pw - margin - 10, summary_y, value)
        summary_y -= 18
    
    # Final Balance
    c.setLineWidth(2)
    c.line(margin, summary_y + 5, pw - margin, summary_y + 5)
    summary_y -= 20
    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin + 10, summary_y, "FINAL BALANCE (CARRY FORWARD):")
    c.drawRightString(pw - margin - 10, summary_y, f"₹{ledger_data['final_balance']:,.2f}")
    
    # Footer
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(margin, 20, f"Generated on: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    c.drawRightString(pw - margin, 20, "NAGPUR BHOPAL TRANSPORT COMPANY")
    
    c.showPage()
    c.save()

# --- Process Challans (Original Function) ---
def process_challans(uploaded_file, route_hamali):
    xls = pd.ExcelFile(uploaded_file)
    df = pd.concat([pd.read_excel(uploaded_file, s, dtype=str) for s in xls.sheet_names], ignore_index=True)
    df.columns = [c.strip() for c in df.columns]
    df["DATE"] = df["DATE"].apply(parse_date_flexible)
    df["FROM"] = df["FROM"].apply(clean_city)
    df["TO"] = df["TO"].apply(clean_city)
    df["NAME OF THE DRIVER"] = df["NAME OF THE DRIVER"].apply(clean_driver)
    df["WT"] = df["WT. Kgs."].apply(clean_num)
    df["PKGS"] = df["NO. OF Pkgs"].apply(clean_num)
    df["FREIGHT"] = df["FREIGHT"].apply(clean_num)
    df["AMOUNT"] = df["AMOUNT"].apply(clean_num)
    df["Hire"] = df["Hire"].apply(clean_num)
    
    groups = df.groupby([df["S. NO."], df["DATE"], df["NAME OF THE DRIVER"], df["FROM"], df["TO"]])
    month_wise_data = {}
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
        
        if month_key not in month_wise_data:
            month_wise_data[month_key] = {}
        if route_key not in month_wise_data[month_key]:
            month_wise_data[month_key][route_key] = []
        month_wise_data[month_key][route_key].append((fname, pdf_buffer.getvalue()))
    
    progress_bar.progress(1.0)
    status_text.text("✅ Challans processing complete!")
    return month_wise_data, challan_counter

# --- NEW: Process Weekly Ledgers ---
def process_weekly_ledgers(uploaded_file, manual_corrections):
    xls = pd.ExcelFile(uploaded_file)
    df = pd.concat([pd.read_excel(uploaded_file, s, dtype=str) for s in xls.sheet_names], ignore_index=True)
    df.columns = [c.strip() for c in df.columns]
    
    # Clean data
    df["DATE"] = df["DATE"].apply(parse_date_flexible)
    df["FROM"] = df["FROM"].apply(clean_city)
    df["TO"] = df["TO"].apply(clean_city)
    df["CONSIGNOR"] = df["CONSIGNOR"].str.upper().str.strip()
    df["CONSIGNEE"] = df["CONSIGNEE"].str.upper().str.strip()
    df["WT"] = df["WT. Kgs."].apply(clean_num)
    df["PKGS"] = df["NO. OF Pkgs"].apply(clean_num)
    df["AMOUNT"] = df["AMOUNT"].apply(clean_num)
    df["Hire"] = df["Hire"].apply(clean_num)
    
    # Filter only Delhi-Mumbai routes
    df = df[((df["FROM"] == "DELHI") & (df["TO"] == "MUMBAI")) | 
            ((df["FROM"] == "MUMBAI") & (df["TO"] == "DELHI"))]
    
    # Add week information
    df["WEEK"] = df["DATE"].apply(lambda x: get_week_range(x)[0] if not pd.isna(x) else 0)
    df["WEEK_RANGE"] = df["DATE"].apply(lambda x: get_week_range(x)[1] if not pd.isna(x) else "")
    
    # Group by Consignor, Week, Route
    ledgers = []
    grouped = df.groupby(["CONSIGNOR", "WEEK_RANGE", "FROM", "TO"])
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    total_groups = len(grouped)
    
    for idx, ((consignor, week_range, from_city, to_city), grp) in enumerate(grouped):
        progress_bar.progress((idx + 1) / total_groups)
        status_text.text(f"Processing ledger {idx + 1}/{total_groups}...")
        
        route = f"{from_city} → {to_city}"
        loading_charge, unloading_charge = get_route_charges(from_city, to_city)
        
        entries = []
        for _, row in grp.iterrows():
            entries.append({
                'date': row['DATE'].strftime('%d %b') if not pd.isna(row['DATE']) else '',
                'consignee': row['CONSIGNEE'],
                'wt': row['WT'],
                'pkgs': row['PKGS'],
                'amount': row['AMOUNT']
            })
        
        total_wt = grp['WT'].sum()
        total_pkgs = grp['PKGS'].sum()
        total_amount = grp['AMOUNT'].sum()
        total_trips = len(grp)
        hire = grp['Hire'].sum()
        
        # Get manual corrections for this ledger
        correction_key = f"{consignor}_{week_range}_{route}"
        corrections = manual_corrections.get(correction_key, {
            'previous_balance': 0,
            'manual_deduction': 0,
            'manual_addition': 0
        })
        
        final_balance = (total_amount + 
                        corrections['previous_balance'] - 
                        loading_charge - 
                        unloading_charge - 
                        hire - 
                        corrections['manual_deduction'] + 
                        corrections['manual_addition'])
        
        ledger_data = {
            'consignor': consignor,
            'week_range': week_range,
            'route': route,
            'entries': entries,
            'total_wt': total_wt,
            'total_pkgs': total_pkgs,
            'total_trips': total_trips,
            'total_amount': total_amount,
            'loading_charge': loading_charge,
            'unloading_charge': unloading_charge,
            'hire': hire,
            'previous_balance': corrections['previous_balance'],
            'manual_deduction': corrections['manual_deduction'],
            'manual_addition': corrections['manual_addition'],
            'final_balance': final_balance
        }
        
        ledgers.append(ledger_data)
    
    progress_bar.progress(1.0)
    status_text.text("✅ Ledgers processing complete!")
    return ledgers

# --- Main App ---
def main():
    st.set_page_config(
        page_title="Transport Manager Pro",
        page_icon="🚚",
        layout="wide"
    )
    
    st.markdown("""
    <div class="main-header">
        <h1>🚚 Transport Manager Pro</h1>
        <p style="font-size: 1.2rem;">Challans & Weekly Ledgers - Complete Solution</p>
    </div>
    """, unsafe_allow_html=True)
    
    with st.sidebar:
        st.image("https://img.icons8.com/clouds/200/000000/truck.png", width=150)
        st.title("📋 Features")
        st.markdown("""
        ✅ **Challan Generation**  
        ✅ **Weekly Ledgers**  
        ✅ **Consignor-wise Reports**  
        ✅ **Manual Corrections**  
        ✅ **Outstanding Balance**  
        ✅ **Route-wise Analytics**  
        """)
    
    tab1, tab2 = st.tabs(["🚀 Generate Challans", "📊 Weekly Ledgers"])
    
    # TAB 1: Challan Generation
    with tab1:
        st.markdown("### 📤 Upload Excel for Challan Generation")
        uploaded_file_challan = st.file_uploader(
            "Choose your transport data file",
            type=['xlsx', 'xls'],
            key="challan_upload"
        )
        
        route_hamali = None
        if uploaded_file_challan:
            xls = pd.ExcelFile(uploaded_file_challan)
            df = pd.concat([pd.read_excel(uploaded_file_challan, s, dtype=str) for s in xls.sheet_names], ignore_index=True)
            df["FROM"] = df["FROM"].apply(clean_city)
            df["TO"] = df["TO"].apply(clean_city)
            routes = sorted({(row["FROM"], row["TO"]) for _, row in df.iterrows() if row["FROM"] and row["TO"]})
            
            st.markdown("### 🛣️ Set Hamali For Each Route")
            route_hamali = {}
            for route_from, route_to in routes:
                colA, colB, colC = st.columns([3, 2, 2])
                route_key = f"{route_from}_TO_{route_to}"
                with colA:
                    st.markdown(f"**{route_from} → {route_to}**")
                with colB:
                    hamali_loading = st.number_input(
                        f"Loading ({route_from} → {route_to})", 
                        min_value=0, value=1700, key=f"load_{route_key}")
                with colC:
                    hamali_unloading = st.number_input(
                        f"Unloading ({route_from} → {route_to})", 
                        min_value=0, value=1700, key=f"unload_{route_key}")
                route_hamali[route_key] = {"loading": hamali_loading, "unloading": hamali_unloading}
        
        if uploaded_file_challan and route_hamali and st.button("🎯 Generate Challans", type="primary"):
            with st.spinner("Processing..."):
                month_wise_data, challan_count = process_challans(uploaded_file_challan, route_hamali)
                
                st.success(f"✅ Generated {challan_count} Challans!")
                
                # Download ZIP
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    for month_key, routes in month_wise_data.items():
                        for route_key, files in routes.items():
                            for fname, pdf_data in files:
                                zip_file.writestr(f"{month_key}/{route_key}/{fname}", pdf_data)
                zip_buffer.seek(0)
                
                st.download_button(
                    label="📦 Download All Challans (ZIP)",
                    data=zip_buffer,
                    file_name=f"Challans_{datetime.now().strftime('%Y%m%d')}.zip",
                    mime="application/zip",
                    use_container_width=True
                )
    
    # TAB 2: Weekly Ledgers
    with tab2:
        st.markdown("### 📤 Upload Excel for Weekly Ledger Generation")
        uploaded_file_ledger = st.file_uploader(
            "Choose your transport data file",
            type=['xlsx', 'xls'],
            key="ledger_upload"
        )
        
        if uploaded_file_ledger:
            # Preview unique consignors
            xls = pd.ExcelFile(uploaded_file_ledger)
            df_preview = pd.concat([pd.read_excel(uploaded_file_ledger, s, dtype=str) for s in xls.sheet_names], ignore_index=True)
            df_preview["DATE"] = df_preview["DATE"].apply(parse_date_flexible)
            df_preview["FROM"] = df_preview["FROM"].apply(clean_city)
            df_preview["TO"] = df_preview["TO"].apply(clean_city)
            df_preview["CONSIGNOR"] = df_preview["CONSIGNOR"].str.upper().str.strip()
            
            # Filter Delhi-Mumbai routes
            df_preview = df_preview[((df_preview["FROM"] == "DELHI") & (df_preview["TO"] == "MUMBAI")) | 
                                   ((df_preview["FROM"] == "MUMBAI") & (df_preview["TO"] == "DELHI"))]
            
            df_preview["WEEK_RANGE"] = df_preview["DATE"].apply(lambda x: get_week_range(x)[1] if not pd.isna(x) else "")
            
            # Get unique consignor-week-route combinations
            unique_combos = df_preview.groupby(["CONSIGNOR", "WEEK_RANGE", "FROM", "TO"]).size().reset_index(name='count')
            
            st.markdown(f"### 📋 Found {len(unique_combos)} Ledger Entries")
            st.dataframe(unique_combos, use_container_width=True)
            
            # Manual Corrections UI
            st.markdown("### 💰 Manual Corrections (Optional)")
            st.info("Set previous balance, deductions, or additions for specific ledgers")
            
            manual_corrections = {}
            
            with st.expander("⚙️ Configure Manual Corrections", expanded=False):
                for idx, row in unique_combos.iterrows():
                    consignor = row['CONSIGNOR']
                    week_range = row['WEEK_RANGE']
                    route = f"{row['FROM']} → {row['TO']}"
                    correction_key = f"{consignor}_{week_range}_{route}"
                    
                    st.markdown(f"**{consignor}** | {week_range} | {route}")
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        prev_bal = st.number_input(
                            "Previous Balance",
                            value=0.0,
                            step=100.0,
                            key=f"prev_{correction_key}"
                        )
                    with col2:
                        deduction = st.number_input(
                            "Deduction",
                            value=0.0,
                            step=100.0,
                            key=f"ded_{correction_key}"
                        )
                    with col3:
                        addition = st.number_input(
                            "Addition",
                            value=0.0,
                            step=100.0,
                            key=f"add_{correction_key}"
                        )
                    
                    manual_corrections[correction_key] = {
                        'previous_balance': prev_bal,
                        'manual_deduction': deduction,
                        'manual_addition': addition
                    }
                    st.markdown("---")
            
            # Generate Ledgers Button
            if st.button("📊 Generate Weekly Ledgers", type="primary", use_container_width=True):
                with st.spinner("Generating ledgers..."):
                    ledgers = process_weekly_ledgers(uploaded_file_ledger, manual_corrections)
                    
                    st.markdown(f"""
                    <div class="success-message">
                        <h3>✅ Success! Generated {len(ledgers)} Weekly Ledgers</h3>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Generate PDFs
                    ledger_pdfs = []
                    for ledger in ledgers:
                        pdf_buffer = io.BytesIO()
                        draw_ledger_pdf(pdf_buffer, ledger)
                        pdf_buffer.seek(0)
                        
                        safe_consignor = ledger['consignor'].replace(" ", "_").replace("/", "-")
                        safe_week = ledger['week_range'].replace(" ", "_").replace("–", "-")
                        safe_route = ledger['route'].replace(" ", "_").replace("→", "to")
                        filename = f"LEDGER_{safe_consignor}_{safe_week}_{safe_route}.pdf"
                        
                        ledger_pdfs.append((filename, pdf_buffer.getvalue(), ledger))
                    
                    # Create ZIP file
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                        for filename, pdf_data, _ in ledger_pdfs:
                            zip_file.writestr(filename, pdf_data)
                    zip_buffer.seek(0)
                    
                    # Download All Button
                    st.download_button(
                        label="📦 Download All Ledgers (ZIP)",
                        data=zip_buffer,
                        file_name=f"Weekly_Ledgers_{datetime.now().strftime('%Y%m%d')}.zip",
                        mime="application/zip",
                        use_container_width=True
                    )
                    
                    st.markdown("---")
                    st.markdown("### 📄 Individual Ledgers")
                    
                    # Display ledgers in expandable cards
                    for filename, pdf_data, ledger in ledger_pdfs:
                        with st.expander(f"📋 {ledger['consignor']} | {ledger['week_range']} | {ledger['route']}", expanded=False):
                            st.markdown(f"""
                            <div class="ledger-card">
                                <h4>{ledger['consignor']}</h4>
                                <p><strong>Week:</strong> {ledger['week_range']}</p>
                                <p><strong>Route:</strong> {ledger['route']}</p>
                                <hr>
                                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                                    <div><strong>Total Weight:</strong> {ledger['total_wt']:,.0f} KG</div>
                                    <div><strong>Total Packages:</strong> {ledger['total_pkgs']:,}</div>
                                    <div><strong>Total Trips:</strong> {ledger['total_trips']}</div>
                                    <div><strong>Total Amount:</strong> ₹{ledger['total_amount']:,.2f}</div>
                                </div>
                                <hr>
                                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                                    <div><strong>Loading Charge:</strong> ₹{ledger['loading_charge']:,.0f}</div>
                                    <div><strong>Unloading Charge:</strong> ₹{ledger['unloading_charge']:,.0f}</div>
                                    <div><strong>Hire:</strong> ₹{ledger['hire']:,.0f}</div>
                                    <div><strong>Previous Balance:</strong> ₹{ledger['previous_balance']:,.2f}</div>
                                    <div><strong>Deduction:</strong> ₹{ledger['manual_deduction']:,.2f}</div>
                                    <div><strong>Addition:</strong> ₹{ledger['manual_addition']:,.2f}</div>
                                </div>
                                <hr>
                                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 15px; border-radius: 8px; text-align: center;">
                                    <h3 style="margin: 0;">FINAL BALANCE: ₹{ledger['final_balance']:,.2f}</h3>
                                    <p style="margin: 5px 0 0 0; font-size: 0.9em;">Carry Forward to Next Week</p>
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            # Transaction Details Table
                            st.markdown("**Transaction Details:**")
                            trans_data = []
                            for entry in ledger['entries']:
                                trans_data.append({
                                    'Date': entry['date'],
                                    'Consignee': entry['consignee'],
                                    'Weight (KG)': f"{entry['wt']:,.0f}",
                                    'Packages': f"{entry['pkgs']:,.0f}",
                                    'Amount': f"₹{entry['amount']:,.2f}"
                                })
                            st.dataframe(pd.DataFrame(trans_data), use_container_width=True)
                            
                            # Download individual PDF
                            st.download_button(
                                label="⬇️ Download This Ledger",
                                data=pdf_data,
                                file_name=filename,
                                mime="application/pdf",
                                key=f"download_{filename}",
                                use_container_width=True
                            )
                    
                    # Summary Statistics
                    st.markdown("---")
                    st.markdown("### 📈 Summary Statistics")
                    
                    total_amount_all = sum(l['total_amount'] for l in ledgers)
                    total_balance_all = sum(l['final_balance'] for l in ledgers)
                    total_trips_all = sum(l['total_trips'] for l in ledgers)
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.markdown(f"""
                        <div class="stats-box">
                            <h2>₹{total_amount_all:,.0f}</h2>
                            <p>Total Revenue</p>
                        </div>
                        """, unsafe_allow_html=True)
                    with col2:
                        st.markdown(f"""
                        <div class="stats-box">
                            <h2>₹{total_balance_all:,.0f}</h2>
                            <p>Total Outstanding</p>
                        </div>
                        """, unsafe_allow_html=True)
                    with col3:
                        st.markdown(f"""
                        <div class="stats-box">
                            <h2>{total_trips_all}</h2>
                            <p>Total Trips</p>
                        </div>
                        """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()