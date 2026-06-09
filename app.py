from flask import Flask, render_template, request, redirect, session, jsonify, send_file
from db import get_connection
import pandas as pd
from docx import Document
from reportlab.pdfgen import canvas
import io
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle
import os
from num2words import num2words

from datetime import datetime, timedelta
import calendar

app = Flask(__name__)
app.secret_key = "gny_secret_key"




# ================= HOME =================
@app.route("/", methods=["GET", "POST"])
def home():

    conn = get_connection()
    cursor = conn.cursor()

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        cursor.execute("""
            SELECT * FROM admin_users
            WHERE username=%s AND password=%s
        """, (username, password))

        user = cursor.fetchone()

        if user:
            session["admin"] = True
            session["username"] = user[1]
            return redirect("/admin")

        return render_template("home.html", error="Invalid login")

    return render_template("home.html")


# ================= APPLY =================
@app.route("/apply", methods=["GET", "POST"])
def apply():

    conn = get_connection()
    cursor = conn.cursor()

    if request.method == "POST":

        d = request.form

        full_name = d["full_name"]
        cid = d["cid"]
        phone = d["phone"]

        dzongkhag = d["dzongkhag"]
        location = d["location"]
        building = d["building"]
        unit_type = d["unit_type"]
        unit_no = d["unit_no"]

        # ================= VALIDATION =================
        error = None

        if not cid.isdigit() or len(cid) != 11:
            error = "CID must be exactly 11 digits"

        elif not phone.isdigit() or len(phone) != 8:
            error = "Phone number must be exactly 8 digits"

        elif not dzongkhag or not location or not building or not unit_type or not unit_no:
            error = "Please select all property details"

        if error:
            return render_template("apply.html", error=error)


        # ================= INSERT APPLICATION =================
        cursor.execute("""
            INSERT INTO applications
            (full_name, cid, phone, dzongkhag, location, building, unit_type, unit_no)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            full_name,
            cid,
            phone,
            dzongkhag,
            location,
            building,
            unit_type,
            unit_no
        ))


        # ================= MARK UNIT OCCUPIED =================
        cursor.execute("""
            UPDATE properties
            SET status='Occupied'
            WHERE dzongkhag=%s
            AND location=%s
            AND building_name=%s
            AND unit_type=%s
            AND unit_no=%s
        """, (
            dzongkhag,
            location,
            building,
            unit_type,
            unit_no
        ))

        conn.commit()
        conn.close()

        return render_template("apply.html", success="Application submitted successfully")


    return render_template("apply.html")


# ================= TRACK =================
@app.route("/track", methods=["GET", "POST"])
def track():

    results = None
    cid = None

    if request.method == "POST":

        cid = request.form["cid"]

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT 
                application_id,
                full_name,
                cid,
                phone,
                dzongkhag,
                location,
                building,
                unit_type,
                unit_no,
                status,
                applied_at
            FROM applications
            WHERE cid=%s
            ORDER BY applied_at DESC
        """, (cid,))

        results = cursor.fetchall()
        conn.close()

    return render_template("track.html", results=results, cid=cid)
# ================= ADMIN =================

@app.route("/admin")
def admin():

    if not session.get("admin"):
        return redirect("/")

    return render_template("admin_home.html")


# ================= HOME PAGE =================
@app.route("/admin/home")
def admin_home():

    if not session.get("admin"):
        return redirect("/")

    selected_dz = request.args.get("dzongkhag")

    conn = get_connection()
    cursor = conn.cursor()

    # ================= TOTAL APPLICATIONS =================
    if selected_dz:
        cursor.execute("SELECT COUNT(*) FROM applications WHERE dzongkhag=%s", (selected_dz,))
    else:
        cursor.execute("SELECT COUNT(*) FROM applications")

    total = cursor.fetchone()[0]

    # ================= PENDING =================
    if selected_dz:
        cursor.execute("""
            SELECT COUNT(*) FROM applications
            WHERE dzongkhag=%s AND status='Pending'
        """, (selected_dz,))
    else:
        cursor.execute("""
            SELECT COUNT(*) FROM applications
            WHERE status='Pending'
        """)

    pending = cursor.fetchone()[0]

    # ================= APPROVED =================
    if selected_dz:
        cursor.execute("""
            SELECT COUNT(*) FROM applications
            WHERE dzongkhag=%s AND status='Approved'
        """, (selected_dz,))
    else:
        cursor.execute("""
            SELECT COUNT(*) FROM applications
            WHERE status='Approved'
        """)

    approved = cursor.fetchone()[0]

    # ================= REJECTED =================
    if selected_dz:
        cursor.execute("""
            SELECT COUNT(*) FROM applications
            WHERE dzongkhag=%s AND status='Rejected'
        """, (selected_dz,))
    else:
        cursor.execute("""
            SELECT COUNT(*) FROM applications
            WHERE status='Rejected'
        """)

    rejected = cursor.fetchone()[0]

    # ================= DZONGKHAG LIST =================
    cursor.execute("SELECT DISTINCT dzongkhag FROM applications")
    dzongkhags = [r[0] for r in cursor.fetchall()]

    # ================= AVAILABLE UNITS =================
    if selected_dz:
        cursor.execute("""
            SELECT dzongkhag, location, COUNT(*)
            FROM properties
            WHERE status='Available' AND dzongkhag=%s
            GROUP BY dzongkhag, location
        """, (selected_dz,))
    else:
        cursor.execute("""
            SELECT dzongkhag, location, COUNT(*)
            FROM properties
            WHERE status='Available'
            GROUP BY dzongkhag, location
        """)

    available_units = cursor.fetchall()

    conn.close()

    return render_template(
        "admin_home.html",
        total=total,
        pending=pending,
        approved=approved,
        rejected=rejected,
        dzongkhags=dzongkhags,
        available_units=available_units,
        selected_dz=selected_dz
    )

# ================= MANAGE APPLICATION =================
@app.route("/admin/applications")
def manage_applications():

    if not session.get("admin"):
        return redirect("/")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            application_id,
            full_name,
            cid,
            phone,
            dzongkhag,
            location,
            building,
            unit_type,
            unit_no,
            status
        FROM applications
        ORDER BY application_id DESC
    """)

    data = cursor.fetchall()
    conn.close()

    return render_template("manage_applications.html", data=data)

@app.route("/update_status/<int:app_id>/<action>")
def update_status(app_id, action):

    conn = get_connection()
    cursor = conn.cursor()

    if action == "approve":
        status = "Approved"
    elif action == "reject":
        status = "Rejected"
    else:
        status = "Pending"

    cursor.execute("""
        UPDATE applications
        SET status=%s
        WHERE application_id=%s
    """, (status, app_id))

    conn.commit()
    conn.close()

    return redirect("/admin/applications")



# ================= INVOICE PAGE =================
@app.route("/admin/invoice", methods=["GET", "POST"])
def invoice():

    if not session.get("admin"):
        return redirect("/")

    # ================= LOAD PAGE =================
    if request.method == "GET":
        return render_template("invoice.html")

    # ================= PREVIEW (NOT SAVED) =================
    data = request.json

    tenant = data["tenant"]
    cid = data["cid"]
    building = data["building"]
    unit = data["unit"]
    items = data["items"]

    total_rent = 0
    total_gst = 0
    months = []

    for i in items:
        rent = float(i["rent"])
        gst = rent * 0.05

        total_rent += rent
        total_gst += gst
        months.append(i["month"])

    grand_total = total_rent + total_gst
    month_range = f"{months[0]} - {months[-1]}" if months else ""

    return jsonify({
        "tenant": tenant,
        "cid": cid,
        "building": building,
        "unit": unit,
        "items": items,
        "total_rent": total_rent,
        "total_gst": total_gst,
        "grand_total": grand_total,
        "month_range": month_range
    })


# ================= SUBMIT (SAVE TO DB) =================
from datetime import datetime

@app.route("/admin/invoice/submit", methods=["POST"])
def invoice_submit():

    if not session.get("admin"):
        return redirect("/")

    data = request.json
    conn = get_connection()
    cursor = conn.cursor()

    items = data.get("items", [])

    # ================= INSERT INVOICE (HEADER) =================
    cursor.execute("""
        INSERT INTO invoices (
            tenant_name,
            cid_no,
            building_name,
            unit_no,
            invoice_date,
            total_rent,
            total_gst,
            grand_total,
            phone,
            plot_no
        )
        VALUES (%s,%s,%s,%s,CURDATE(),%s,%s,%s,%s,%s)
    """, (
        data["tenant"],
        data["cid"],
        data["building"],
        data["unit"],
        data["total_rent"],
        data["total_gst"],
        data["grand_total"],
        data.get("phone"),
        data.get("plot")
    ))

    invoice_id = cursor.lastrowid

    # ================= GENERATE INVOICE NO =================
    year = datetime.now().year

    cursor.execute("""
        SELECT invoice_no
        FROM invoices
        WHERE invoice_no LIKE %s
        ORDER BY id DESC
        LIMIT 1
    """, (f"GNY/RED/{year}/%",))

    last = cursor.fetchone()

    if last:
        last_number = int(last[0].split("/")[-1])
        next_number = last_number + 1
    else:
        next_number = 1

    invoice_no = f"GNY/RED/{year}/{next_number:04d}"

    cursor.execute("""
        UPDATE invoices
        SET invoice_no=%s
        WHERE id=%s
    """, (invoice_no, invoice_id))

    # ================= INSERT INVOICE ITEMS =================
    for i in items:
        rent = float(i["rent"])
        gst = rent * 0.05
        total = rent + gst

        cursor.execute("""
            INSERT INTO invoice_items (
                invoice_no,
                month,
                rent,
                gst,
                total,
                remarks
            )
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (
            invoice_no,
            i["month"],
            rent,
            gst,
            total,
            i.get("remarks", "")
        ))

    # ================= FETCH MONTHS =================
    cursor.execute("""
        SELECT month
        FROM invoice_items
        WHERE invoice_no=%s
        ORDER BY id ASC
    """, (invoice_no,))

    raw_months = [m[0] for m in cursor.fetchall()]

    # ================= CONVERT TO Jan-2026 FORMAT =================
    formatted_months = []
    parsed_dates = []

    for m in raw_months:
        try:
            dt = datetime.strptime(m, "%Y-%m")
            formatted_months.append(dt.strftime("%b-%Y"))
            parsed_dates.append(dt)
        except:
            formatted_months.append(m)

    # ================= MONTH RANGE =================
    def format_month_range(dates, original):
        if not dates:
            return ""

        try:
            start = min(dates)
            end = max(dates)

            if start.year == end.year:
                return f"{start.strftime('%b')}-{end.strftime('%b %Y')}"
            else:
                return f"{start.strftime('%b %Y')}-{end.strftime('%b %Y')}"

        except:
            return f"{original[0]}-{original[-1]}"

    month_range = format_month_range(parsed_dates, formatted_months)

    # ================= UPDATE INVOICE TABLE =================
    cursor.execute("""
        UPDATE invoices
        SET month_range=%s
        WHERE invoice_no=%s
    """, (month_range, invoice_no))

    conn.commit()
    conn.close()

    return jsonify({
        "invoice_no": invoice_no,
        "month_range": month_range
    })


@app.route("/admin/invoice/pdf/<path:invoice_no>", methods=["GET"])
def invoice_pdf(invoice_no):

    conn = get_connection()
    cursor = conn.cursor()

    # ================= HEADER =================
    cursor.execute("""
        SELECT tenant_name,
               cid_no,
               phone,
               plot_no,
               building_name,
               unit_no,
               invoice_date,
               total_rent,
               total_gst,
               grand_total
        FROM invoices
        WHERE invoice_no=%s
    """, (invoice_no,))

    row = cursor.fetchone()

    if not row:
        return "Invoice not found", 404

    tenant, cid, phone, plot_no, building, unit, invoice_date, total_rent, total_gst, grand_total = row

    # ================= ITEMS =================
    cursor.execute("""
        SELECT month, rent, gst, total, remarks
        FROM invoice_items
        WHERE invoice_no=%s
        ORDER BY id ASC
    """, (invoice_no,))

    items = cursor.fetchall()

    # ================= MONTH RANGE =================
    months = [i[0] for i in items]

    def format_month_range(month_list):
        if not month_list:
            return ""

        try:
            dates = [datetime.strptime(m, "%Y-%m") for m in month_list]
            start = min(dates)
            end = max(dates)

            if start.year == end.year:
                return f"{start.strftime('%b')}–{end.strftime('%b %Y')}"
            else:
                return f"{start.strftime('%b %Y')}–{end.strftime('%b %Y')}"
        except:
            return f"{month_list[0]}–{month_list[-1]}"

    month_range = format_month_range(months)

    conn.close()


    # ================= PDF =================
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # ================= WATERMARK =================
    try:
        p.saveState()
        p.setFillAlpha(0.08)
        p.drawImage("static/logo.png", width/2-200, height/2-200, 400, 400, mask='auto')
        p.restoreState()
    except:
        pass

    # ================= HEADER IMAGE (CENTERED PRO) =================
    try:
        header_path = "static/Picture.png"
        img_width = width
        img_height = 100
        p.drawImage(
            header_path,
            0,
            height - img_height,
            width=img_width,
            height=img_height,
            preserveAspectRatio=True,
            mask='auto'
            )
    except Exception as e:
        print("Header image not found:", e)
    
    # ================= INVOICE INFO =================
    p.setFont("Helvetica", 10)
# ================= LEFT SIDE (INVOICE INFO) =================
    p.drawString(40, height - 120, f"Invoice No: {invoice_no}")
    p.drawString(40, height - 135, f"Date: {invoice_date}")
    
    
    p.drawString(300, height - 120, f"Tenant Name: {tenant}")
    p.drawString(300, height - 135, f"CID: {cid}")
    p.drawString(300, height - 150, f"Phone Number: {phone}")
    p.drawString(300, height - 165, f"Plot No: {plot_no}")
    p.drawString(300, height - 180, f"Building: {building}")
    p.drawString(300, height - 195, f"Unit: {unit}")

   

    # ================= MAIN TABLE =================

    
    table_data = [["Sl", "Month", "Rent", "GST", "Total", "Remarks"]]
    for i, r in enumerate(items, start=1):
        try:
            
            month_display = datetime.strptime(str(r[0]), "%Y-%m").strftime("%b-%Y")
        except:
            month_display = str(r[0])
        table_data.append([
            i,
            month_display,
            f"Nu. {float(r[1]):,.2f}",
            f"Nu. {float(r[2]):,.2f}",
            f"Nu. {float(r[3]):,.2f}",
            r[4] if r[4] else ""
        ])
    table = Table(table_data, colWidths=[30, 120, 90, 90, 90, 120])

    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1F4EAA")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("FONTSIZE", (0,0), (-1,-1), 9),
    ]))

    table.wrapOn(p, width, height)
    table.drawOn(p, 40, height - 290)

    # ================= SUMMARY TABLE =================
    summary = [
        ["Total Rent", f"Nu. {total_rent:,.2f}"],
        ["Total GST", f"Nu. {total_gst:,.2f}"],
        ["Grand Total", f"Nu. {grand_total:,.2f}"]
    ]
    t = Table(summary, colWidths=[150, 150])
    t.setStyle(TableStyle([
        
        ("GRID", (0,0), (-1,-1), 0.5, colors.black),
        ("FONTNAME", (0,2), (-1,2), "Helvetica-Bold"),
        ("FONTSIZE", (0,2), (-1,2), 11),
        ("BACKGROUND", (0,2), (-1,2), colors.HexColor("#D9E2F3")),
        ("ALIGN", (0,0), (-1,-1), "LEFT")
        ]))
    t.wrapOn(p, width, height)
    t.drawOn(p, 40, height - 370)

    
    # ================= IN WORDS =================
    from textwrap import wrap
    words = num2words(grand_total, lang='en').capitalize()
    
    p.setFont("Helvetica-Bold", 10)
    p.drawString(40, height - 390, "Amount in Words:")
    
    p.setFont("Helvetica", 10)
    
    wrapped = wrap(f"Ngultrum. {words} only", 95)
    y = height - 405
    for line in wrapped:
        p.drawString(40, y, line)
        y -= 14

    # ================= BANK DETAILS =================
    p.setFont("Helvetica", 9)
    p.drawString(40, 120, "Received By: Accounts")
    p.drawString(40, 105, "Bank: Bank of Bhutan (BOB)")
    p.drawString(40, 90, "Account: Gerab Revenue Account")
    p.drawString(40, 75, "Acc No: 215001353")

    # ================= SIGNATURE =================
    p.setFont("Helvetica-Bold", 10)
    p.drawString(400, 90, "Authorized Sign & Seal")

    p.save()

    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"{invoice_no}.pdf")

@app.route("/admin/invoice/download/<invoice_no>")
def download_invoice(invoice_no):

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
                   SELECT tenant_name, cid_no, building_name, unit_no,
                   invoice_date, month_range,
                   total_rent, total_gst, grand_total,
                   remarks, due_date, phone, plot_no
                   FROM invoices
                   WHERE invoice_no=%s
                   """, (invoice_no,))
    row = cursor.fetchone()
    conn.close()

    if not row or not row[0]:
        return "PDF not found", 404

    pdf_data = row[0]

    return send_file(
        io.BytesIO(pdf_data),
        as_attachment=True,
        download_name=f"{invoice_no}.pdf",
        mimetype="application/pdf"
    )

# ================= LOGOUT =================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ================= DYNAMIC DROPDOWNS (DATABASE DRIVEN) =================

@app.route("/api/dzongkhags")
def dzongkhags():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT dzongkhag
        FROM properties
        WHERE status='Available'
    """)

    data = [i[0] for i in cursor.fetchall()]
    conn.close()
    return jsonify(data)


@app.route("/api/locations/<dz>")
def locations(dz):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT location
        FROM properties
        WHERE dzongkhag=%s AND status='Available'
    """, (dz,))

    data = [i[0] for i in cursor.fetchall()]
    conn.close()
    return jsonify(data)


@app.route("/api/buildings/<dz>/<loc>")
def buildings(dz, loc):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT building_name
        FROM properties
        WHERE dzongkhag=%s
        AND location=%s
        AND status='Available'
    """, (dz, loc))

    data = [i[0] for i in cursor.fetchall()]
    conn.close()
    return jsonify(data)


@app.route("/api/unit-types/<dz>/<loc>/<b>")
def unit_types(dz, loc, b):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT unit_type
        FROM properties
        WHERE dzongkhag=%s
        AND location=%s
        AND building_name=%s
        AND status='Available'
    """, (dz, loc, b))

    data = [i[0] for i in cursor.fetchall()]
    conn.close()
    return jsonify(data)


@app.route("/api/units/<dz>/<loc>/<b>/<ut>")
def units(dz, loc, b, ut):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT unit_no
        FROM properties
        WHERE dzongkhag=%s
        AND location=%s
        AND building_name=%s
        AND unit_type=%s
        AND status='Available'
    """, (dz, loc, b, ut))

    data = [i[0] for i in cursor.fetchall()]
    conn.close()
    return jsonify(data)


if __name__ == "__main__":
    app.run(debug=True)