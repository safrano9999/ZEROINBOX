from __future__ import annotations

import os
import re
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

from .models import SortResult


DEST_COLORS = {
    "loeschen": "#dc2626",
    "uncertain": "#d97706",
    "newsletter": "#2563eb",
    "bezahlt": "#16a34a",
    "agb": "#6b7280",
    "welcome": "#7c3aed",
    "freitag": "#0891b2",
    "kommunikation": "#059669",
    "systemmeldungen": "#475569",
}
DEFAULT_DEST_COLOR = "#1a2b4a"


def _he(value: object) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(value or ""))
    return escape(text)


def report_dir(config: dict[str, Any]) -> Path:
    configured = str(config.get("_reportDir") or "").strip()
    return Path(configured).expanduser() if configured else Path(str(config["_baseDir"])) / "REPORTS"


def write_pdf_report(
    config: dict[str, Any],
    run_id: str,
    account: str,
    dry_run: bool,
    moved: int,
    results: list[SortResult],
) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.colors import HexColor
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import HRFlowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    output_dir = report_dir(config)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"zeroinbox-{run_id}.pdf"

    dark = HexColor("#1a2b4a")
    light = HexColor("#f1f5f9")
    mid = HexColor("#64748b")
    white = colors.white
    width, _height = A4
    margin = 18 * mm
    usable = width - 2 * margin

    def style(name: str, **kwargs: Any) -> ParagraphStyle:
        return ParagraphStyle(name, **kwargs)

    title_style = style("title", fontName="Helvetica-Bold", fontSize=30, textColor=white, leading=36)
    subtitle_style = style(
        "subtitle", fontName="Helvetica", fontSize=11, textColor=HexColor("#94a3b8"), leading=16
    )
    h2_style = style("h2", fontName="Helvetica-Bold", fontSize=13, textColor=dark, leading=18)
    h3_style = style("h3", fontName="Helvetica-Bold", fontSize=11, textColor=dark, leading=16)
    body_style = style("body", fontName="Helvetica", fontSize=10, textColor=HexColor("#334155"), leading=15)
    label_style = style(
        "label", fontName="Helvetica-Bold", fontSize=8, textColor=mid, leading=12, spaceAfter=1
    )
    subject_style = style("subj", fontName="Helvetica-Bold", fontSize=17, textColor=dark, leading=24)
    nav_left_style = style("navl", fontName="Helvetica-Bold", fontSize=9, textColor=mid, leading=13)
    nav_right_style = style(
        "navr", fontName="Helvetica", fontSize=9, textColor=mid, leading=13, alignment=TA_RIGHT
    )
    badge_style = style(
        "badge", fontName="Helvetica-Bold", fontSize=12, textColor=white, leading=16, alignment=TA_CENTER
    )
    mono_style = style("mono", fontName="Courier", fontSize=9, textColor=HexColor("#475569"), leading=13)

    try:
        timestamp = datetime.strptime(run_id, "%Y%m%d-%H%M%S").strftime("%Y-%m-%d_%H-%M-%S")
    except ValueError:
        timestamp = run_id
    model = os.environ.get("ZEROINBOX_OPENAI_V1_DEFAULT_LLM") or str(config.get("defaultModel") or "")
    total = len(results)
    elems: list[Any] = []

    header = Table(
        [[Paragraph("ZEROINBOX", title_style), Paragraph(f"AI Mail Report<br/><font size='10'>{timestamp}</font>", subtitle_style)]],
        colWidths=[usable * 0.55, usable * 0.45],
    )
    header.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), dark),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (0, -1), 16),
                ("RIGHTPADDING", (1, 0), (1, -1), 16),
                ("TOPPADDING", (0, 0), (-1, -1), 16),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ]
        )
    )
    elems.append(header)
    elems.append(Spacer(1, 5 * mm))

    info_row = Table(
        [
            [
                Paragraph(f"<b>Model</b><br/>{_he(model)}", body_style),
                Paragraph(f"<b>Accounts</b><br/>{_he(account)}", body_style),
                Paragraph(f"<b>Sorted</b><br/>{total} email{'s' if total != 1 else ''}", body_style),
            ]
        ],
        colWidths=[usable / 3] * 3,
    )
    info_row.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), light),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEAFTER", (0, 0), (-2, -1), 0.5, HexColor("#cbd5e1")),
            ]
        )
    )
    elems.append(info_row)
    elems.append(Spacer(1, 6 * mm))

    destination_counts: dict[str, int] = {}
    for result in results:
        destination_counts[result.destination] = destination_counts.get(result.destination, 0) + 1

    if destination_counts:
        elems.append(Paragraph("By destination", h2_style))
        elems.append(Spacer(1, 2 * mm))
        stat_data: list[list[Any]] = []
        stat_style: list[tuple[Any, ...]] = [
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (0, -1), 8),
            ("LEFTPADDING", (1, 0), (1, -1), 10),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]
        for index, (destination, count) in enumerate(
            sorted(destination_counts.items(), key=lambda item: -item[1])
        ):
            color = DEST_COLORS.get(destination, DEFAULT_DEST_COLOR)
            destination_style = style(
                f"bdg_{index}",
                fontName="Helvetica-Bold",
                fontSize=9,
                textColor=white,
                leading=12,
                alignment=TA_CENTER,
            )
            stat_data.append([Paragraph(destination.upper(), destination_style), Paragraph(str(count), body_style)])
            stat_style.append(("BACKGROUND", (0, index), (0, index), HexColor(color)))

        stats = Table(stat_data, colWidths=[42 * mm, usable - 42 * mm])
        stats.setStyle(TableStyle(stat_style))
        elems.append(stats)
        elems.append(Spacer(1, 7 * mm))

    elems.append(Paragraph("All sorted emails", h2_style))
    elems.append(Spacer(1, 2 * mm))

    column_widths = [10 * mm, 58 * mm, usable - 10 * mm - 58 * mm - 38 * mm, 38 * mm]
    list_rows: list[list[Any]] = [
        [
            Paragraph("#", label_style),
            Paragraph("FROM", label_style),
            Paragraph("SUBJECT", label_style),
            Paragraph("DESTINATION", label_style),
        ]
    ]
    list_style: list[tuple[Any, ...]] = [
        ("BACKGROUND", (0, 0), (-1, 0), dark),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, HexColor("#e2e8f0")),
    ]
    for index, result in enumerate(results):
        row_background = white if index % 2 == 0 else light
        destination_color = DEST_COLORS.get(result.destination, DEFAULT_DEST_COLOR)
        destination_style = style(
            f"lb_{index}",
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=white,
            leading=11,
            alignment=TA_CENTER,
        )
        list_rows.append(
            [
                Paragraph(str(index + 1), body_style),
                Paragraph(_he(result.sender[:42]), mono_style),
                Paragraph(_he((result.subject or "(no subject)")[:65]), body_style),
                Paragraph(result.destination.upper(), destination_style),
            ]
        )
        list_style.append(("BACKGROUND", (0, index + 1), (2, index + 1), row_background))
        list_style.append(("BACKGROUND", (3, index + 1), (3, index + 1), HexColor(destination_color)))

    email_table = Table(list_rows, colWidths=column_widths, repeatRows=1)
    email_table.setStyle(TableStyle(list_style))
    elems.append(email_table)

    for index, result in enumerate(results):
        elems.append(PageBreak())
        destination_color = HexColor(DEST_COLORS.get(result.destination, DEFAULT_DEST_COLOR))
        source = " / ".join(item for item in (result.source_account, result.source_mailbox) if item) or account
        nav = Table(
            [
                [
                    Paragraph(_he(source.upper()), nav_left_style),
                    Paragraph(f"{index + 1} &nbsp;/&nbsp; {total}", nav_right_style),
                ]
            ],
            colWidths=[usable * 0.5, usable * 0.5],
        )
        nav.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), light),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (0, -1), 10),
                    ("RIGHTPADDING", (1, 0), (1, -1), 10),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        elems.append(nav)
        elems.append(Spacer(1, 5 * mm))
        elems.append(Paragraph(_he(result.subject or "(no subject)"), subject_style))
        elems.append(Spacer(1, 5 * mm))
        elems.append(HRFlowable(width=usable, color=HexColor("#e2e8f0"), thickness=1))
        elems.append(Spacer(1, 5 * mm))

        mail_info = f"<b>From</b><br/>{_he(result.sender)}<br/><br/><b>Date</b><br/>{_he(result.date)}"
        details = Table(
            [[Paragraph(mail_info, body_style), Paragraph(result.destination.upper(), badge_style)]],
            colWidths=[usable * 0.62, usable * 0.38],
        )
        details.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (1, 0), (1, 0), destination_color),
                    ("VALIGN", (0, 0), (0, 0), "TOP"),
                    ("VALIGN", (1, 0), (1, 0), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                    ("LEFTPADDING", (0, 0), (0, -1), 0),
                    ("LEFTPADDING", (1, 0), (1, -1), 10),
                    ("RIGHTPADDING", (1, 0), (1, -1), 10),
                ]
            )
        )
        elems.append(details)
        elems.append(Spacer(1, 6 * mm))
        elems.append(HRFlowable(width=usable, color=HexColor("#e2e8f0"), thickness=1))
        elems.append(Spacer(1, 5 * mm))

        if result.summary:
            elems.append(Paragraph("Summary", h3_style))
            elems.append(Spacer(1, 2 * mm))
            elems.append(Paragraph(_he(result.summary), body_style))
            elems.append(Spacer(1, 5 * mm))
        if result.reason:
            elems.append(Paragraph("Reason", h3_style))
            elems.append(Spacer(1, 2 * mm))
            elems.append(Paragraph(_he(result.reason), body_style))
            elems.append(Spacer(1, 5 * mm))

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
        title="ZeroInbox Report",
        author="ZEROINBOX",
    )
    doc.build(elems)
    return output_path
