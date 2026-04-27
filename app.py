from flask import Flask, render_template, request, jsonify, make_response
from io import BytesIO
import re
import html

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, HRFlowable
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024  # 1MB max

# ── Constants ──────────────────────────────────────────────────────────────
MONTHS = [
    "January","February","March","April","May","June",
    "July","August","September","October","November","December"
]

BLUE       = colors.HexColor('#2563EB')
BLUE_DARK  = colors.HexColor('#1D4ED8')
BLUE_LIGHT = colors.HexColor('#EFF6FF')
BLUE_BORDER= colors.HexColor('#BFDBFE')
TEXT       = colors.HexColor('#0F172A')
TEXT_MUTED = colors.HexColor('#64748B')
GREY_BG    = colors.HexColor('#F7F8FA')
GREY_LINE  = colors.HexColor('#E2E6ED')

# ── Validation ─────────────────────────────────────────────────────────────

def sanitize(value, max_len=100):
    if not isinstance(value, str):
        return ""
    return html.escape(value.strip()[:max_len])

def parse_amount(value, field_name):
    try:
        v = float(str(value).strip().replace(",", ""))
        if v < 0:
            raise ValueError(f"{field_name} cannot be negative.")
        if v > 10_000_000:
            raise ValueError(f"{field_name} value seems unrealistic.")
        return round(v, 2)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a valid number.")

def validate_pan(pan):
    if not pan:
        return ""
    pan = pan.strip().upper()
    if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', pan):
        raise ValueError("PAN number format is invalid (e.g. ABCDE1234F).")
    return pan

def validate_month(month):
    if month not in MONTHS:
        raise ValueError("Invalid month selected.")
    return month

def validate_year(year):
    try:
        y = int(year)
        if y < 2000 or y > 2100:
            raise ValueError()
        return y
    except (TypeError, ValueError):
        raise ValueError("Invalid year.")

def fmt(n):
    """Format number as Indian rupee string."""
    return f"\u20b9{float(str(n).replace(',','').replace('\u20b9','')):,.2f}"

# ── PDF builder ────────────────────────────────────────────────────────────

def build_pdf(ctx):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm,
        topMargin=16*mm,  bottomMargin=16*mm
    )

    W = A4[0] - 36*mm  # usable width

    def ps(name, **kw):
        base = dict(fontName='Helvetica', fontSize=9, textColor=TEXT, leading=13)
        base.update(kw)
        return ParagraphStyle(name, **base)

    s_normal   = ps('normal')
    s_bold     = ps('bold',   fontName='Helvetica-Bold')
    s_muted    = ps('muted',  textColor=TEXT_MUTED, fontSize=8)
    s_right    = ps('right',  alignment=TA_RIGHT)
    s_bold_r   = ps('bold_r', fontName='Helvetica-Bold', alignment=TA_RIGHT)
    s_small    = ps('small',  fontSize=7.5, textColor=TEXT_MUTED)
    s_net_lbl  = ps('net_lbl',fontName='Helvetica-Bold', fontSize=9,  textColor=BLUE_DARK)
    s_net_amt  = ps('net_amt',fontName='Helvetica-Bold', fontSize=15, textColor=BLUE_DARK, alignment=TA_RIGHT)

    story = []

    # ── Header ──
    hdr = Table([[
        Paragraph(
            f'<font size="13"><b>{ctx["company_name"]}</b></font><br/>'
            f'<font size="8" color="#64748B">{ctx["company_addr"]}</font>',
            s_normal
        ),
        Paragraph(
            f'<font size="13" color="#2563EB"><b>PAYSLIP</b></font><br/>'
            f'<font size="9" color="#64748B">{ctx["month"]} {ctx["year"]}</font>',
            ps('hdr_r', alignment=TA_RIGHT)
        ),
    ]], colWidths=[W*0.6, W*0.4])
    hdr.setStyle(TableStyle([
        ('VALIGN',      (0,0), (-1,-1), 'TOP'),
        ('LINEBELOW',   (0,0), (-1,0),  1.5, BLUE),
        ('BOTTOMPADDING',(0,0),(-1,0),  10),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING',(0,0), (-1,-1), 0),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 10))

    # ── Employee row ──
    def emp_cell(label, value):
        return Paragraph(
            f'<font size="7" color="#94A3B8"><b>{label}</b></font><br/>'
            f'<font size="9"><b>{value or "—"}</b></font>',
            s_normal
        )

    emp = Table([[
        emp_cell("EMPLOYEE NAME", ctx['emp_name']),
        emp_cell("EMPLOYEE ID",   ctx['emp_id'] or "—"),
        emp_cell("DESIGNATION",   ctx['designation'] or "—"),
        emp_cell("DEPARTMENT",    ctx['department'] or "—"),
        emp_cell("PAN",           ctx['pan'] or "—"),
    ]], colWidths=[W/5]*5)
    emp.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,-1), GREY_BG),
        ('BOX',           (0,0), (-1,-1), 0.5, GREY_LINE),
        ('TOPPADDING',    (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('LEFTPADDING',   (0,0), (-1,-1), 8),
        ('RIGHTPADDING',  (0,0), (-1,-1), 8),
        ('VALIGN',        (0,0), (-1,-1), 'TOP'),
    ]))
    story.append(emp)
    story.append(Spacer(1, 12))

    # ── Salary tables ──
    col_w = (W - 8) / 2

    def amount_val(key):
        return float(str(ctx[key]).replace(',','').replace('\u20b9',''))

    # Earnings
    earn_rows = [
        [Paragraph('<b>Earnings</b>', ps('eh', fontName='Helvetica-Bold', fontSize=8, textColor=TEXT_MUTED)), ''],
        ['Basic Salary',      fmt(ctx['basic'])],
        ['HRA',               fmt(ctx['hra'])],
        ['Special Allowance', fmt(ctx['special'])],
    ]
    if amount_val('other_earn') > 0:
        earn_rows.append([ctx['other_earn_label'], fmt(ctx['other_earn'])])
    earn_rows.append([Paragraph('<b>Gross Salary</b>', s_bold),
                      Paragraph(f'<b>{fmt(ctx["gross"])}</b>', s_bold_r)])

    # Deductions
    ded_rows = [
        [Paragraph('<b>Deductions</b>', ps('dh', fontName='Helvetica-Bold', fontSize=8, textColor=TEXT_MUTED)), ''],
        ['Provident Fund (PF)', fmt(ctx['pf'])],
    ]
    if amount_val('pt') > 0:
        ded_rows.append(['Professional Tax', fmt(ctx['pt'])])
    if amount_val('tds') > 0:
        ded_rows.append(['TDS', fmt(ctx['tds'])])
    if amount_val('other_ded') > 0:
        ded_rows.append([ctx['other_ded_label'], fmt(ctx['other_ded'])])
    ded_rows.append([Paragraph('<b>Total Deductions</b>', s_bold),
                     Paragraph(f'<b>{fmt(ctx["total_ded"])}</b>', s_bold_r)])

    # Pad to equal length
    while len(earn_rows) < len(ded_rows): earn_rows.insert(-1, ['', ''])
    while len(ded_rows) < len(earn_rows): ded_rows.insert(-1, ['', ''])

    def make_col(rows):
        n = len(rows)
        t = Table(rows, colWidths=[col_w*0.65, col_w*0.35])
        t.setStyle(TableStyle([
            ('FONTNAME',      (0,0), (-1,-1), 'Helvetica'),
            ('FONTSIZE',      (0,0), (-1,-1), 9),
            ('TEXTCOLOR',     (0,0), (-1,-1), TEXT),
            ('ALIGN',         (1,0), (1,-1),  'RIGHT'),
            ('BACKGROUND',    (0,0), (-1,0),  GREY_BG),
            ('TOPPADDING',    (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ('LEFTPADDING',   (0,0), (-1,-1), 8),
            ('RIGHTPADDING',  (0,0), (-1,-1), 8),
            ('LINEBELOW',     (0,0), (-1,0),  0.5, GREY_LINE),
            ('LINEABOVE',     (0,n-1), (-1,n-1), 0.5, GREY_LINE),
            ('BACKGROUND',    (0,n-1), (-1,n-1), GREY_BG),
            ('BOX',           (0,0), (-1,-1), 0.5, GREY_LINE),
        ]))
        return t

    salary = Table(
        [[make_col(earn_rows), make_col(ded_rows)]],
        colWidths=[col_w, col_w]
    )
    salary.setStyle(TableStyle([
        ('LEFTPADDING',   (0,0), (-1,-1), 0),
        ('RIGHTPADDING',  (0,0), (-1,-1), 0),
        ('TOPPADDING',    (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('VALIGN',        (0,0), (-1,-1), 'TOP'),
        ('RIGHTPADDING',  (0,0), (0,0),   8),
    ]))
    story.append(salary)
    story.append(Spacer(1, 10))

    # ── Net Pay ──
    net = Table(
        [[Paragraph('NET PAY (TAKE HOME)', s_net_lbl),
          Paragraph(f'<b>{fmt(ctx["net_pay"])}</b>', s_net_amt)]],
        colWidths=[W*0.5, W*0.5]
    )
    net.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,-1), BLUE_LIGHT),
        ('BOX',           (0,0), (-1,-1), 0.75, BLUE_BORDER),
        ('TOPPADDING',    (0,0), (-1,-1), 10),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
        ('LEFTPADDING',   (0,0), (-1,-1), 14),
        ('RIGHTPADDING',  (0,0), (-1,-1), 14),
        ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(net)
    story.append(Spacer(1, 14))

    # ── Footer ──
    story.append(HRFlowable(width=W, thickness=0.5, color=GREY_LINE))
    story.append(Spacer(1, 6))
    footer = Table([[
        Paragraph('This is a computer-generated payslip and does not require a signature.', s_small),
        Paragraph('Generated via PaySlipFree.com',
                  ps('gen', fontSize=7.5, textColor=colors.HexColor('#CBD5E1'), alignment=TA_RIGHT)),
    ]], colWidths=[W*0.65, W*0.35])
    footer.setStyle(TableStyle([
        ('LEFTPADDING',  (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING',   (0,0), (-1,-1), 0),
        ('BOTTOMPADDING',(0,0), (-1,-1), 0),
    ]))
    story.append(footer)

    doc.build(story)
    return buffer.getvalue()


# ── Routes ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", months=MONTHS)

@app.route("/payslip-generator/")
@app.route("/payslip-generator")
def payslip_generator():
    return render_template("payslip_generator.html", months=MONTHS)

@app.route("/payslip-generator/preview", methods=["POST"])
def preview():
    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({"error": "Invalid request."}), 400

        basic      = parse_amount(data.get("basic", 0),     "Basic Salary")
        hra        = parse_amount(data.get("hra", 0),        "HRA")
        special    = parse_amount(data.get("special", 0),    "Special Allowance")
        other_earn = parse_amount(data.get("other_earn", 0), "Other Allowance")

        pf_mode = data.get("pf_mode", "auto")
        pf = round(basic * 0.12, 2) if pf_mode == "auto" else parse_amount(data.get("pf_manual", 0), "PF")

        pt        = parse_amount(data.get("pt", 0),        "Professional Tax")
        tds       = parse_amount(data.get("tds", 0),       "TDS")
        other_ded = parse_amount(data.get("other_ded", 0), "Other Deduction")

        gross     = round(basic + hra + special + other_earn, 2)
        total_ded = round(pf + pt + tds + other_ded, 2)
        net_pay   = round(gross - total_ded, 2)

        if net_pay < 0:
            return jsonify({"error": "Deductions exceed gross salary."}), 400

        return jsonify({"gross": gross, "pf": pf, "total_ded": total_ded, "net_pay": net_pay})

    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/payslip-generator/download", methods=["POST"])
def download():
    errors = []

    try:
        emp_name    = sanitize(request.form.get("emp_name", ""), 80)
        emp_id      = sanitize(request.form.get("emp_id", ""), 30)
        designation = sanitize(request.form.get("designation", ""), 80)
        department  = sanitize(request.form.get("department", ""), 80)
        pan = ""

        if not emp_name:
            errors.append("Employee name is required.")
        try:
            pan = validate_pan(request.form.get("pan", ""))
        except ValueError as e:
            errors.append(str(e))

        company_name = sanitize(request.form.get("company_name", ""), 100)
        company_addr = sanitize(request.form.get("company_addr", ""), 200)
        if not company_name:
            errors.append("Company name is required.")

        try:
            month = validate_month(request.form.get("month", ""))
        except ValueError as e:
            errors.append(str(e))
            month = ""

        try:
            year = validate_year(request.form.get("year", ""))
        except ValueError as e:
            errors.append(str(e))
            year = ""

        try:
            basic      = parse_amount(request.form.get("basic", 0),     "Basic Salary")
            hra        = parse_amount(request.form.get("hra", 0),        "HRA")
            special    = parse_amount(request.form.get("special", 0),    "Special Allowance")
            other_earn = parse_amount(request.form.get("other_earn", 0), "Other Allowance")
            other_earn_label = sanitize(request.form.get("other_earn_label", "Other Allowance"), 50) or "Other Allowance"
        except ValueError as e:
            errors.append(str(e))
            basic = hra = special = other_earn = 0
            other_earn_label = "Other Allowance"

        if basic == 0 and not errors:
            errors.append("Basic Salary is required.")

        try:
            pf_mode = request.form.get("pf_mode", "auto")
            pf = round(basic * 0.12, 2) if pf_mode == "auto" else parse_amount(request.form.get("pf_manual", 0), "PF")
            pt        = parse_amount(request.form.get("pt", 0),        "Professional Tax")
            tds       = parse_amount(request.form.get("tds", 0),       "TDS")
            other_ded = parse_amount(request.form.get("other_ded", 0), "Other Deduction")
            other_ded_label = sanitize(request.form.get("other_ded_label", "Other Deduction"), 50) or "Other Deduction"
        except ValueError as e:
            errors.append(str(e))
            pf = pt = tds = other_ded = 0
            other_ded_label = "Other Deduction"

        if errors:
            return jsonify({"errors": errors}), 400

        gross     = round(basic + hra + special + other_earn, 2)
        total_ded = round(pf + pt + tds + other_ded, 2)
        net_pay   = round(gross - total_ded, 2)

        if net_pay < 0:
            return jsonify({"errors": ["Deductions exceed gross salary."]}), 400

        def fv(n): return f"{n:,.2f}"

        ctx = dict(
            emp_name=emp_name, emp_id=emp_id,
            designation=designation, department=department, pan=pan,
            company_name=company_name, company_addr=company_addr,
            month=month, year=year,
            basic=fv(basic), hra=fv(hra), special=fv(special),
            other_earn=fv(other_earn), other_earn_label=other_earn_label,
            pf=fv(pf), pt=fv(pt), tds=fv(tds),
            other_ded=fv(other_ded), other_ded_label=other_ded_label,
            gross=fv(gross), total_ded=fv(total_ded), net_pay=fv(net_pay)
        )

        pdf_bytes = build_pdf(ctx)
        filename  = f"payslip_{emp_name.replace(' ','_')}_{month}_{year}.pdf"

        response = make_response(pdf_bytes)
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    except Exception:
        return jsonify({"errors": ["Server error. Please try again."]}), 500


# ── Error handlers ─────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(413)
def too_large(e):
    return jsonify({"errors": ["Request too large."]}), 413

@app.errorhandler(500)
def server_error(e):
    return render_template("500.html"), 500


if __name__ == "__main__":
    app.run(debug=False)
