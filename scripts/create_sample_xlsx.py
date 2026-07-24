"""Generate a sample Caldwell-style medical chronology xlsx for local testing."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

SAMPLE_ROWS = [
    (
        "12/07/2024",
        "Eric Mast, DO; Grant T. Olsen, NP",
        "Fisher-Titus Medical Center",
        "Hand, Neck, Back, Head, Shoulder",
        "Emergency Medicine",
        "Encounter Note",
        "Patient presented after motor vehicle collision with complaints of neck pain, headache, and left shoulder discomfort. "
        "Exam notable for cervical tenderness and reduced range of motion. Discharged with pain management instructions.",
        "https://www.google.com/search?q=sample+encounter+pdf",
    ),
    (
        "12/08/2024",
        "Radiology Dept",
        "Fisher-Titus Medical Center",
        "Neck, Back",
        "Radiology",
        "Imaging Report",
        "CT cervical spine without contrast: no acute fracture or malalignment. Mild soft tissue swelling noted.",
        "https://www.google.com/search?q=sample+imaging+pdf",
    ),
    (
        "12/15/2024",
        "James Caldwell, MD",
        "Orthopedic Associates",
        "Shoulder, Back",
        "Orthopedic",
        "Encounter Note",
        "Follow-up for persistent shoulder and low back pain. Plan includes physical therapy referral and continued conservative management.",
        "https://www.google.com/search?q=sample+ortho+pdf",
    ),
    (
        "01/03/2025",
        "EMS Transport",
        "Norwalk EMS",
        "Neck, Head",
        "Emergency Medicine",
        "EMS/Ambulance Report",
        "Ambulance transport following reported increase in headache and dizziness. Vital signs stable en route.",
        "https://www.google.com/search?q=sample+ems+pdf",
    ),
]

HEADERS = [
    "Encounter Date",
    "Primary Provider",
    "Facility",
    "Body Parts",
    "Medicine Type",
    "Record Type",
    "Summary",
    "Link To Pdf",
]


def main() -> None:
    output_dir = Path(__file__).resolve().parent.parent / "sample_data"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "Caldwell - Medical Chronology.xlsx"

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Chronology"
    sheet.append(HEADERS)

    for row in SAMPLE_ROWS:
        sheet.append(list(row[:-1]) + ["pdf"])

    link_col = HEADERS.index("Link To Pdf") + 1
    for row_idx, row in enumerate(SAMPLE_ROWS, start=2):
        cell = sheet.cell(row=row_idx, column=link_col)
        cell.hyperlink = row[-1]
        cell.font = Font(color="0563C1", underline="single")

    workbook.save(output_path)
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
