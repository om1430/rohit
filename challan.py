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

# Page configuration
st.set_page_config(
    page_title="Transport Challan Generator Pro",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for professional look
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


# Utility Functions
def parse_date_flexible(date_str):
    """Parse dates in multiple formats"""
    if pd.isna(date_str):
        return pd.NaT
    
    date_str = str(date_str).strip()
    formats = ["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y"]
    
    for fmt in formats:
        try:
            return pd.to_datetime(date_str, format=fmt)
        except:
            continue
    
    try:
        return pd.to_datetime(date_str, dayfirst=True)
    except:
        return pd.NaT


def clean_city(x):
    if not isinstance(x, str):
        return ""
    x = x.upper().strip()
    x = x.replace(".", "").replace(",", "").replace("-", " ").strip()
    return " ".join(x.split())


def clean_driver(x):
    if not isinstance(x, str):
        return "NA"
    x = x.upper().strip()
    if x in ["", "NA", "N/A", "NONE", "-", "--"]:
        return "NA"
    return " ".join(x.split())


def clean_num(x):
    try:
        val = float(str(x).strip())
        return val if not pd.isna(val) else 0
    except:
        return 0


def draw_pdf(pdf_buffer, meta, rows):
    """Generate challan PDF"""
    c = canvas.Canvas(pdf_buffer, pagesize=A4)
    pw, ph = A4
    margin = 15 * mm

    # Header
    c.setFont("Helvetica-Bold", 16)
    title = "NAGPUR BHOPAL TRANSPORT COMPANY"
    title_width = c.stringWidth(title, "Helvetica-Bold", 16)
    c.drawString((pw - title_width) / 2, ph - 35, title)

    c.setFont("Helvetica-Bold", 12)
    route_text = f"{meta['FROM']} TO {meta['TO']} - {meta['month']}"
    route_width = c.stringWidth(route_text, "Helvetica-Bold", 12)
    c.drawString((pw - route_width) / 2, ph - 53, route_text)

    # Metadata grid
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

    # Table
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

    # Summary
    summary_y = table_start_y - h - 25
    c.setFont("Helvetica", 11)
    c.drawString(margin + 8, summary_y, "GADI BHADAA")
    c.drawRightString(pw - margin - 8, summary_y, str(int(meta['hire'])))
    
    summary_y -= 18
    c.drawString(margin + 8, summary_y, "HAMLI")
    c.drawRightString(pw - margin - 8, summary_y, str(int(meta['hamli'])))
    
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
    """Generate summary report PDF with multi-page support"""
    c = canvas.Canvas(pdf_buffer, pagesize=A4)
    pw, ph = A4
    margin = 15 * mm
    
    # Calculate totals first
    totals = {"qty": 0, "weight": 0, "topay": 0, "hire": 0, "hamali": 0, "balance": 0}
    for row in summary_rows:
        for key in totals:
            totals[key] += float(row[key]) if row[key] else 0
    
    # Rows per page calculation
    # Available height after header = ph - 80 (header) - 40 (margin for total)
    available_height = ph - 120
    row_height = 20  # Approximate height per row
    rows_per_page = int(available_height / row_height) - 1  # -1 for header row
    
    # Split data into pages
    total_data_rows = len(summary_rows)
    num_pages = (total_data_rows + rows_per_page - 1) // rows_per_page
    
    for page_num in range(num_pages):
        # Draw header on each page
        c.setFont("Helvetica-Bold", 18)
        title = f"{route_from} TO {route_to} - {month_year}"
        title_width = c.stringWidth(title, "Helvetica-Bold", 18)
        c.drawString((pw - title_width) / 2, ph - 40, title)
        
        # Page number if multiple pages
        if num_pages > 1:
            c.setFont("Helvetica", 10)
            page_text = f"Page {page_num + 1} of {num_pages}"
            c.drawString(pw - margin - 80, ph - 40, page_text)
        
        table_start_y = ph - 80
        
        # Prepare table data for this page
        table_data = [["Date", "Truck No.", "Chal- No.", "QTY", "Weight", "Topay",
                       "Hire", "Hamali", "Balance - AMT"]]
        
        # Get rows for this page
        start_idx = page_num * rows_per_page
        end_idx = min(start_idx + rows_per_page, total_data_rows)
        
        for row in summary_rows[start_idx:end_idx]:
            table_data.append([
                row["date"], row["truck_no"], row["challan_no"], row["qty"],
                row["weight"], row["topay"], row["hire"], row["hamali"], row["balance"]
            ])
        
        # Add TOTAL row only on the last page
        if page_num == num_pages - 1:
            table_data.append([
                "TOTAL", "", "", str(int(totals["qty"])), str(int(totals["weight"])),
                str(round(totals["topay"], 1)), str(int(totals["hire"])),
                str(int(totals["hamali"])), str(round(totals["balance"], 1))
            ])
        
        col_widths = [55, 60, 50, 40, 50, 55, 50, 50, 70]
        table = Table(table_data, colWidths=col_widths)
        
        # Base style
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
            ('LINEBELOW', (0, 0), (-1, 0), 2, colors.black),
        ]
        
        # Add total row styling only on last page
        if page_num == num_pages - 1:
            style.extend([
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#FFD966')),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, -1), (-1, -1), 10),
                ('LINEABOVE', (0, -1), (-1, -1), 2, colors.black),
            ])
        
        table.setStyle(TableStyle(style))
        
        w, h = table.wrap(0, 0)
        table.drawOn(c, margin, table_start_y - h)
        
        c.showPage()
    
    c.save()


def process_excel_file(uploaded_file):
    """Main processing function - Organized by MONTH first, then ROUTE"""
    
    # Read Excel
    xls = pd.ExcelFile(uploaded_file)
    df = pd.concat([pd.read_excel(uploaded_file, s, dtype=str) for s in xls.sheet_names],
                   ignore_index=True)
    
    df["DATE_RAW"] = df["DATE"]
    df.columns = [c.strip() for c in df.columns]
    df["DATE"] = df["DATE"].apply(parse_date_flexible)
    
    # Clean data
    df["FROM"] = df["FROM"].apply(clean_city)
    df["TO"] = df["TO"].apply(clean_city)
    df["NAME OF THE DRIVER"] = df["NAME OF THE DRIVER"].apply(clean_driver)
    
    df["WT"] = df["WT. Kgs."].apply(clean_num)
    df["PKGS"] = df["NO. OF Pkgs"].apply(clean_num)
    df["FREIGHT"] = df["FREIGHT"].apply(clean_num)
    df["AMOUNT"] = df["AMOUNT"].apply(clean_num)
    df["Hire"] = df["Hire"].apply(clean_num)
    
    # Group by serial number
    groups = df.groupby([df["S. NO."], df["DATE"], df["NAME OF THE DRIVER"], 
                         df["FROM"], df["TO"]])
    
    # 🗂️ NEW STRUCTURE: Month → Route → Files
    month_wise_data = {}  # {"September_2024": {"MUMBAI_TO_DELHI": [files], ...}}
    route_summaries = {}  # For summary reports per route per month
    challan_counter = 0
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total_groups = len(groups)
    
    for idx, ((serial_no, date, driver, FROM, TO), grp) in enumerate(groups):
        challan_counter += 1
        
        # Update progress
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
        hamali = 1700
        other_exp = 0
        balance = total_amount - hire - hamali - other_exp
        
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
            "hamli": hamali,
            "other_exp": other_exp,
            "balance": balance
        }
        
        # Generate PDF
        pdf_buffer = io.BytesIO()
        draw_pdf(pdf_buffer, meta, rows)
        pdf_buffer.seek(0)
        
        safe_serial = str(serial_no).replace("/", "-").replace("\\", "-").replace(" ", "_")
        fname = f"{date.strftime('%Y%m%d')}__{safe_serial}__{driver.replace(' ','_')}__{FROM}_to_{TO}.pdf"
        
        # 🗂️ Organize by MONTH first, then ROUTE
        month_key = date.strftime("%B_%Y") if not pd.isna(date) else "Unknown_Month"
        route_key = f"{FROM}_TO_{TO}"
        
        if month_key not in month_wise_data:
            month_wise_data[month_key] = {}
        
        if route_key not in month_wise_data[month_key]:
            month_wise_data[month_key][route_key] = []
        
        month_wise_data[month_key][route_key].append((fname, pdf_buffer.getvalue()))
        
        # Collect summary data
        summary_key = (month_key, FROM, TO)
        if summary_key not in route_summaries:
            route_summaries[summary_key] = []
        
        route_summaries[summary_key].append({
            "date": date.strftime("%d/%m/%Y") if not pd.isna(date) else "",
            "truck_no": meta["truck"],
            "challan_no": str(serial_no),
            "qty": str(int(total_pkgs)),
            "weight": str(int(total_wt)),
            "topay": str(round(total_amount, 1)),
            "hire": str(int(hire)),
            "hamali": str(int(hamali)),
            "balance": str(round(balance, 1))
        })
    
    # Generate summary PDFs for each month-route combination
    status_text.text("Generating summary reports...")
    
    for (month_key, route_from, route_to), summary_rows in route_summaries.items():
        summary_rows.sort(key=lambda x: x["date"])
        
        pdf_buffer = io.BytesIO()
        month_display = month_key.replace("_", " ")
        draw_summary_pdf(pdf_buffer, route_from, route_to, month_display.upper(), summary_rows)
        pdf_buffer.seek(0)
        
        route_key = f"{route_from}_TO_{route_to}"
        fname = f"SUMMARY__{route_from}_TO_{route_to}__{month_key}.pdf"
        
        # Add summary to the same month-route folder
        if month_key not in month_wise_data:
            month_wise_data[month_key] = {}
        if route_key not in month_wise_data[month_key]:
            month_wise_data[month_key][route_key] = []
            
        month_wise_data[month_key][route_key].append((fname, pdf_buffer.getvalue()))
    
    progress_bar.progress(1.0)
    status_text.text("✅ Processing complete!")
    
    return month_wise_data, challan_counter, len(route_summaries)


# Main App
def main():
    # Header
    st.markdown("""
    <div class="main-header">
        <h1>🚚 Transport Challan Generator Pro</h1>
        <p style="font-size: 1.2rem;">Professional PDF Challans & Reports in Seconds</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        st.image("https://img.icons8.com/clouds/200/000000/truck.png", width=150)
        st.title("📋 Features")
        st.markdown("""
        ✅ **Multi-sheet Excel support**  
        ✅ **Auto route detection**  
        ✅ **Professional PDF design**  
        ✅ **Summary reports**  
        ✅ **Bulk download (ZIP)**  
        ✅ **Smart date parsing**  
        ✅ **Color-coded tables**  
        """)
        
        st.divider()
        st.markdown("### 💡 Quick Tips")
        st.info("Upload Excel with columns: S. NO., DATE, FROM, TO, CONSIGNOR, CONSIGNEE, etc.")
        
        st.divider()
        st.markdown("### 📞 Support")
        st.markdown("Need help? Contact us!")
    
    # Main content
    tab1, tab2, tab3 = st.tabs(["🚀 Generate", "📖 How It Works", "💼 Pricing"])
    
    with tab1:
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.markdown("### 📤 Upload Your Excel File")
            uploaded_file = st.file_uploader(
                "Choose your transport data file",
                type=['xlsx', 'xls'],
                help="Upload Excel with transport data"
            )
        
        with col2:
            st.markdown("### ⚙️ Settings")
            hamali_amount = st.number_input("Hamali Amount", value=1700, step=100)
            other_exp = st.number_input("Other Expenses", value=0, step=100)
        
        if uploaded_file:
            st.markdown("---")
            
            if st.button("🎯 Generate Challans & Reports", type="primary", use_container_width=True):
                with st.spinner("Processing your file..."):
                    try:
                        month_wise_data, challan_count, summary_count = process_excel_file(uploaded_file)
                        
                        # Success message
                        st.markdown(f"""
                        <div class="success-message">
                            <h3>✅ Success! Generated {challan_count} Challans & {summary_count} Summary Reports</h3>
                            <p>Organized by {len(month_wise_data)} month(s)</p>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # Stats
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
                        
                        # Download options
                        st.markdown("### 📥 Download Your Files")
                        
                        # Create ZIP with MONTH-WISE structure
                        zip_buffer = io.BytesIO()
                        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                            for month_key, routes in month_wise_data.items():
                                for route_key, files in routes.items():
                                    for fname, pdf_data in files:
                                        # Structure: September_2024/MUMBAI_TO_DELHI/challan.pdf
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
                        
                        # 🗂️ Month-wise Preview with Route breakdown
                        st.markdown("### 📅 Month-wise Organization")
                        
                        # Sort months chronologically
                        sorted_months = sorted(month_wise_data.keys(), 
                                             key=lambda x: datetime.strptime(x, "%B_%Y") if x != "Unknown_Month" else datetime.min)
                        
                        for month_key in sorted_months:
                            routes = month_wise_data[month_key]
                            month_display = month_key.replace("_", " ")
                            
                            # Month expander
                            with st.expander(f"📅 **{month_display}** - {len(routes)} Routes", expanded=True):
                                
                                # Stats for this month
                                month_total_files = sum(len(files) for files in routes.values())
                                st.info(f"📊 **Total Files:** {month_total_files} (Challans + Summary Reports)")
                                
                                # Download this month's files
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
                                
                                # Route-wise breakdown within this month
                                for route_key, files in routes.items():
                                    route_display = route_key.replace("_TO_", " → ")
                                    
                                    col1, col2 = st.columns([3, 1])
                                    with col1:
                                        st.markdown(f"#### 🛣️ {route_display}")
                                        st.caption(f"{len(files)} files (Challans + Summary)")
                                    
                                    with col2:
                                        # Download this specific route
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
                                    
                                    # Show file list (first 5 files)
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
    
    with tab2:
        st.markdown("""
        ## 📖 How It Works
        
        ### Step 1: Prepare Your Excel
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
        
        ### Step 2: Upload & Process
        Simply upload your Excel file and click "Generate". The system will:
        - Parse all sheets automatically
        - Clean and validate data
        - Group by routes and serial numbers
        - Generate professional PDFs
        
        ### Step 3: Download
        Get all your challans organized by route in a single ZIP file!
        """)
        
        st.image("https://img.icons8.com/clouds/300/000000/process.png", width=200)
    
    with tab3:
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


if __name__ == "__main__":
    main()