"""
Generate a handful of simple, original born-digital pages (letter, memo,
report-with-table, notice) purely for use as INPUT to the fax / camera-photo /
rotation synthetic-degradation pipeline. These are not meant to be interesting
documents in their own right -- just clean, textual source pages distinct from
every other page in the bench so no single clean render is reused across two
different synthetic categories.
"""
import sys

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

sys.path.insert(0, "/Users/kavy/Code/Projects/jesteruct/bench/vision_bakeoff/data/scripts")


def letter_page(out_pdf, title, paragraphs):
    c = canvas.Canvas(out_pdf, pagesize=LETTER)
    w, h = LETTER
    y = h - 60
    c.setFont("Helvetica-Bold", 16)
    c.drawString(60, y, title)
    y -= 30
    c.setFont("Helvetica", 11)
    for para in paragraphs:
        for line in wrap(para, 90):
            c.drawString(60, y, line)
            y -= 15
        y -= 10
    c.showPage()
    c.save()


def wrap(text, width):
    import textwrap
    return textwrap.wrap(text, width)


def table_report_page(out_pdf, title, rows):
    c = canvas.Canvas(out_pdf, pagesize=LETTER)
    w, h = LETTER
    y = h - 60
    c.setFont("Helvetica-Bold", 16)
    c.drawString(60, y, title)
    y -= 40
    col_x = [60, 220, 340, 440]
    c.setFont("Helvetica-Bold", 10)
    headers = ["Item", "Quantity", "Unit Price", "Total"]
    for x, hd in zip(col_x, headers):
        c.drawString(x, y, hd)
    y -= 6
    c.line(60, y, 520, y)
    y -= 16
    c.setFont("Helvetica", 10)
    for row in rows:
        for x, val in zip(col_x, row):
            c.drawString(x, y, str(val))
        y -= 18
    c.showPage()
    c.save()


if __name__ == "__main__":
    import os
    OUT = "/Users/kavy/Code/Projects/jesteruct/bench/vision_bakeoff/data/raw/synthetic/sources"
    os.makedirs(OUT, exist_ok=True)

    letter_page(
        f"{OUT}/memo_fax1.pdf",
        "Internal Memorandum",
        [
            "To: All Department Heads",
            "From: Office of Facilities Management",
            "Re: Scheduled Maintenance Notice",
            "This is to notify all staff that the west-wing elevator will be taken out of "
            "service for scheduled maintenance beginning Monday at 7:00 AM and continuing "
            "through Wednesday of the same week. Staff requiring wheelchair access should "
            "use the east-wing elevator during this period.",
            "Please direct any questions to the Facilities helpdesk at extension 4471. We "
            "apologize for any inconvenience this may cause and appreciate your patience "
            "while these necessary repairs are completed.",
        ],
    )

    table_report_page(
        f"{OUT}/invoice_fax2.pdf",
        "Purchase Order Summary",
        [
            ["Widget A-100", 12, "$4.50", "$54.00"],
            ["Widget B-200", 5, "$12.00", "$60.00"],
            ["Bracket Set", 30, "$1.25", "$37.50"],
            ["Cable, 2m", 8, "$3.10", "$24.80"],
            ["Mounting Kit", 4, "$9.99", "$39.96"],
        ],
    )

    letter_page(
        f"{OUT}/notice_cam1.pdf",
        "Community Notice Board",
        [
            "The quarterly residents' meeting will be held in the community hall on the "
            "second Thursday of next month at 6:30 PM.",
            "Agenda items include the proposed changes to visitor parking, an update on "
            "the garden renovation project, and open discussion of resident concerns.",
            "All residents are encouraged to attend. Light refreshments will be provided.",
        ],
    )

    table_report_page(
        f"{OUT}/schedule_cam2.pdf",
        "Weekly Shift Schedule",
        [
            ["Monday", "A. Rivera", "08:00-16:00", "Front Desk"],
            ["Tuesday", "J. Chen", "09:00-17:00", "Warehouse"],
            ["Wednesday", "A. Rivera", "08:00-16:00", "Front Desk"],
            ["Thursday", "M. Okafor", "12:00-20:00", "Loading Dock"],
            ["Friday", "J. Chen", "09:00-17:00", "Warehouse"],
        ],
    )

    letter_page(
        f"{OUT}/notice_rotate.pdf",
        "Building Access Notice",
        [
            "Effective immediately, all visitors must sign in at the main reception desk "
            "and wear a visible visitor badge at all times while on the premises.",
            "Badges must be returned to reception upon departure. Staff are asked to "
            "escort visitors in restricted areas and to report any unbadged individuals "
            "to security at extension 2200.",
        ],
    )

    print("wrote 5 source PDFs")
