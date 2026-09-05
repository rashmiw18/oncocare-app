"""
OncoCare AI — PDF report generator
=====================================
Builds a clinical-style PDF summary for a patient over a date range:
cover summary, risk trend chart, vitals averages, flagged readings table,
anomaly count, and any doctor notes. Uses reportlab (Platypus) for layout
and matplotlib for the embedded trend chart.
"""

import io
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, HRFlowable
)
from reportlab.lib.enums import TA_CENTER

BRAND_TEAL = colors.HexColor("#0E2521")
BRAND_MINT = colors.HexColor("#3E9C86")
BRAND_CORAL = colors.HexColor("#D9614A")
BRAND_AMBER = colors.HexColor("#C99A2E")
BRAND_SAFE = colors.HexColor("#4F9A5E")
GREY = colors.HexColor("#5B6B67")

RISK_COLOR_MAP = {"Low": BRAND_SAFE, "Medium": BRAND_AMBER, "High": BRAND_CORAL}


def _trend_chart_image(history):
    timestamps = [datetime.fromisoformat(r["timestamp"].replace("Z", "")) for r in history]
    scores = [r["risk_score"] for r in history]

    fig, ax = plt.subplots(figsize=(6.4, 2.6), dpi=160)
    ax.plot(timestamps, scores, color="#3E9C86", linewidth=2, marker="o", markersize=3)
    ax.fill_between(timestamps, scores, color="#3E9C86", alpha=0.12)
    ax.set_ylim(0, 15)
    ax.set_ylabel("Risk score", fontsize=9)
    ax.tick_params(axis="both", labelsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", linestyle="--", alpha=0.3)
    fig.autofmt_xdate(rotation=25)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf


def _vitals_avg_chart_image(history):
    labels = ["Pain", "Fatigue", "Nausea"]
    avg = [
        sum(r["vitals"]["pain_level"] for r in history) / len(history),
        sum(r["vitals"]["fatigue_level"] for r in history) / len(history),
        sum(r["vitals"]["nausea_level"] for r in history) / len(history),
    ]
    fig, ax = plt.subplots(figsize=(3.0, 2.6), dpi=160)
    bars = ax.bar(labels, avg, color=["#D9614A", "#C99A2E", "#3E9C86"])
    ax.set_ylim(0, 10)
    ax.set_ylabel("Avg (0-10)", fontsize=9)
    ax.tick_params(axis="both", labelsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for b, v in zip(bars, avg):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.2, f"{v:.1f}", ha="center", fontsize=8)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf


def generate_patient_report(patient, doctor, history, notes, start_label, end_label):
    """
    patient: dict (users row) - the patient this report is about
    doctor: dict or None - assigned doctor, if any
    history: list of reading records (dicts) within the selected date range, chronological
    notes: list of doctor note dicts (most recent first)
    Returns: BytesIO of the generated PDF
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        topMargin=0.6 * inch, bottomMargin=0.6 * inch,
        leftMargin=0.65 * inch, rightMargin=0.65 * inch,
        title=f"OncoCare AI Report - {patient['full_name']}"
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleBrand", parent=styles["Title"], textColor=BRAND_TEAL, fontSize=22, spaceAfter=2)
    sub_style = ParagraphStyle("SubBrand", parent=styles["Normal"], textColor=GREY, fontSize=10, spaceAfter=14)
    h2 = ParagraphStyle("H2Brand", parent=styles["Heading2"], textColor=BRAND_TEAL, fontSize=13, spaceBefore=14, spaceAfter=8)
    body = ParagraphStyle("BodyBrand", parent=styles["Normal"], fontSize=9.5, leading=14, textColor=colors.HexColor("#232D2B"))
    small = ParagraphStyle("SmallBrand", parent=styles["Normal"], fontSize=8.2, leading=12, textColor=GREY)

    story = []

    story.append(Paragraph("OncoCare AI &mdash; Patient Health Report", title_style))
    story.append(Paragraph(
        f"Reporting period: {start_label} to {end_label} &nbsp;&middot;&nbsp; "
        f"Generated {datetime.utcnow().strftime('%b %d, %Y %H:%M UTC')}", sub_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#D8E3E0")))
    story.append(Spacer(1, 12))

    doctor_name = doctor["full_name"] if doctor else "Not assigned"
    info_data = [
        ["Patient", patient["full_name"], "Attending physician", doctor_name],
        ["Username", patient["username"], "Readings in period", str(len(history))],
    ]
    info_table = Table(info_data, colWidths=[95, 175, 120, 120])
    info_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), GREY),
        ("TEXTCOLOR", (2, 0), (2, -1), GREY),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTNAME", (3, 0), (3, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.HexColor("#D8E3E0")),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 14))

    if not history:
        story.append(Paragraph("No readings were logged during this period.", body))
        doc.build(story)
        buf.seek(0)
        return buf

    dist = {"Low": 0, "Medium": 0, "High": 0}
    anomaly_count = 0
    for r in history:
        dist[r["risk_level"]] += 1
        if r["is_anomaly"]:
            anomaly_count += 1
    latest = history[-1]
    avg_score = sum(r["risk_score"] for r in history) / len(history)

    summary_data = [
        ["Latest risk level", "Avg. risk score", "Unusual patterns flagged", "High-risk readings"],
        [latest["risk_level"], f"{avg_score:.1f} / 15", str(anomaly_count), str(dist["High"])],
    ]
    summary_table = Table(summary_data, colWidths=[130, 130, 130, 130])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF3F0")),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F7FAF9")),
        ("TEXTCOLOR", (0, 0), (-1, 0), GREY),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTSIZE", (0, 1), (-1, 1), 13),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 1), (0, 1), RISK_COLOR_MAP.get(latest["risk_level"], BRAND_TEAL)),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D8E3E0")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D8E3E0")),
    ]))
    story.append(summary_table)

    story.append(Paragraph("Risk score trend", h2))
    trend_img = _trend_chart_image(history)
    story.append(Image(trend_img, width=6.4 * inch, height=2.6 * inch))

    story.append(Paragraph("Average symptom burden over period", h2))
    bar_img = _vitals_avg_chart_image(history)
    story.append(Image(bar_img, width=3.0 * inch, height=2.6 * inch))

    story.append(Paragraph("Notable readings", h2))
    notable = [r for r in history if r["risk_level"] == "High" or r["is_anomaly"]]
    if notable:
        style_para = ParagraphStyle("cell", parent=body, fontSize=8, leading=10)
        table_data = [["Time", "Temp", "HR", "SpO<sub>2</sub>", "Risk", "Score", "Note"]]
        for r in notable[-15:]:
            ts = datetime.fromisoformat(r["timestamp"].replace("Z", "")).strftime("%b %d %H:%M")
            note_bits = []
            if r["is_anomaly"]:
                note_bits.append("unusual pattern")
            if r["flags"]:
                note_bits.append(f"{len(r['flags'])} vitals out of range")
            table_data.append([
                ts, f"{r['vitals']['temperature']}\u00b0F", f"{r['vitals']['heart_rate']}",
                Paragraph(f"{r['vitals']['spo2']}%", style_para),
                r["risk_level"], f"{r['risk_score']:.1f}",
                Paragraph(", ".join(note_bits) or "-", style_para)
            ])
        notable_table = Table(table_data, colWidths=[62, 42, 34, 50, 42, 40, 150], repeatRows=1)
        notable_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_TEAL),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAF9")]),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D8E3E0")),
        ]))
        story.append(notable_table)
    else:
        story.append(Paragraph("No high-risk or anomalous readings during this period.", body))

    if notes:
        story.append(Paragraph("Clinical notes", h2))
        for n in notes[:10]:
            ts = datetime.fromisoformat(n["timestamp"].replace("Z", "")).strftime("%b %d, %Y %H:%M")
            story.append(Paragraph(f"<b>{ts} &mdash; Dr. {n['doctor_name']}</b>", small))
            story.append(Paragraph(n["note"], body))
            story.append(Spacer(1, 6))

    story.append(Spacer(1, 18))
    story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#D8E3E0")))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "This report is generated by an AI decision-support tool and is not a substitute for "
        "professional medical judgement. It summarizes patient-reported and device-logged vitals "
        "and a statistical risk model's output. Please discuss any concerning trends with the "
        "patient's oncology care team.",
        small
    ))

    doc.build(story)
    buf.seek(0)
    return buf
