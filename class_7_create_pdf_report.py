import sqlite3
from pathlib import Path
from textwrap import shorten

import pandas as pd

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate,
    PageTemplate,
    Frame,
    Paragraph,
    Spacer,
    PageBreak,
    Table,
    TableStyle,
    Flowable,
)
from reportlab.platypus.tableofcontents import TableOfContents


# ==================================================
# Report details
# ==================================================

STUDENT_NAME = "Rabeya Siddika Sajia"
STUDENT_ID = "23084716"
INSTITUTION = "FAU Erlangen-Nürnberg"
SUPERVISOR = "Prof. Dr. Dirk Riehle"
COURSE = "Seeding QDArchive - 10 ECTS Applied Software Engineering Project"
REPOSITORIES_TEXT = "DANS · ICPSR"
CLASSIFIER_NAME = "ISIC Rev. 5 · TF-IDF similarity classifier"
REPORT_DATE = "July 2026"

DB_PATH = Path("db/metadata.db")
OUTPUT_DIR = Path("exports")
OUTPUT_DIR.mkdir(exist_ok=True)

OUTPUT_PDF = OUTPUT_DIR / "23084716-sq26-classification-report.pdf"

CLASSIFIER_VERSION = "tfidf_isic5_division_v1"

REPOSITORY_NAMES = {
    5: "DANS",
    15: "ICPSR",
}


# ==================================================
# Color palette: blue + green, white background
# ==================================================

DARK_BLUE = colors.HexColor("#12355B")
MEDIUM_BLUE = colors.HexColor("#2563EB")
DEEP_GREEN = colors.HexColor("#047857")
SOFT_GREEN = colors.HexColor("#E8F7EF")
SOFT_BLUE = colors.HexColor("#EAF2FF")
LIGHT_GREY = colors.HexColor("#F8FAFC")
GRID_GREY = colors.HexColor("#CBD5E1")
TEXT_DARK = colors.HexColor("#1F2937")
TEXT_MUTED = colors.HexColor("#4B5563")
WHITE = colors.white


# ==================================================
# Styles
# ==================================================

PAGE_SIZE = landscape(A4)
styles = getSampleStyleSheet()

title_style = ParagraphStyle(
    "TitleStyle",
    parent=styles["Title"],
    fontSize=34,
    leading=40,
    alignment=TA_CENTER,
    textColor=DARK_BLUE,
    spaceAfter=2,
)

subtitle_style = ParagraphStyle(
    "SubtitleStyle",
    parent=styles["Title"],
    fontSize=18,
    leading=24,
    alignment=TA_CENTER,
    textColor=DEEP_GREEN,
    spaceAfter=24,
)

h1_style = ParagraphStyle(
    "Heading1Style",
    parent=styles["Heading1"],
    fontSize=19,
    leading=24,
    textColor=DARK_BLUE,
    spaceBefore=10,
    spaceAfter=10,
)

h2_style = ParagraphStyle(
    "Heading2Style",
    parent=styles["Heading2"],
    fontSize=14,
    leading=18,
    textColor=DEEP_GREEN,
    spaceBefore=8,
    spaceAfter=7,
)

body_style = ParagraphStyle(
    "BodyStyle",
    parent=styles["BodyText"],
    fontSize=10.5,
    leading=14,
    textColor=TEXT_DARK,
    spaceAfter=7,
)

small_style = ParagraphStyle(
    "SmallStyle",
    parent=styles["BodyText"],
    fontSize=9,
    leading=12,
    textColor=TEXT_DARK,
)

cover_label_style = ParagraphStyle(
    "CoverLabel",
    parent=body_style,
    fontName="Helvetica-Bold",
    textColor=DARK_BLUE,
    fontSize=10.5,
    leading=14,
)

cover_value_style = ParagraphStyle(
    "CoverValue",
    parent=body_style,
    textColor=TEXT_DARK,
    fontSize=10.5,
    leading=14,
)


# ==================================================
# Helper classes
# ==================================================

class ReportDocTemplate(BaseDocTemplate):
    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph):
            style_name = flowable.style.name
            text = flowable.getPlainText()

            if style_name == "Heading1Style":
                key = "h1-" + text.replace(" ", "-")
                self.canv.bookmarkPage(key)
                self.notify("TOCEntry", (0, text, self.page, key))

            elif style_name == "Heading2Style":
                key = "h2-" + text.replace(" ", "-")
                self.canv.bookmarkPage(key)
                self.notify("TOCEntry", (1, text, self.page, key))


class BarChartFlowable(Flowable):
    def __init__(self, data, title, width=24 * cm, bar_height=0.34 * cm):
        super().__init__()
        self.data = data
        self.title = title
        self.width = width
        self.bar_height = bar_height
        self.label_width = 11.5 * cm
        self.chart_width = self.width - self.label_width - 2.8 * cm
        self.height = 1.5 * cm + len(data) * (bar_height + 0.18 * cm)

    def wrap(self, availWidth, availHeight):
        return self.width, self.height

    def draw(self):
        c = self.canv

        c.setFillColor(DARK_BLUE)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(0, self.height - 0.4 * cm, self.title)

        if not self.data:
            c.setFillColor(TEXT_MUTED)
            c.setFont("Helvetica", 9)
            c.drawString(0, self.height - 1.0 * cm, "No classified projects available.")
            return

        max_count = max(row["count"] for row in self.data)
        y = self.height - 1.15 * cm

        for row in self.data:
            label = f"{row['primary_class']} - {row['primary_class_name']}"
            label = shorten(label, width=72, placeholder="...")

            count = int(row["count"])
            bar_width = (count / max_count) * self.chart_width if max_count else 0

            c.setFillColor(TEXT_DARK)
            c.setFont("Helvetica", 8)
            c.drawString(0, y, label)

            c.setFillColor(DEEP_GREEN)
            c.rect(
                self.label_width,
                y - 0.05 * cm,
                bar_width,
                self.bar_height,
                fill=1,
                stroke=0,
            )

            c.setFillColor(DARK_BLUE)
            c.setFont("Helvetica-Bold", 8.5)
            c.drawString(self.label_width + bar_width + 0.1 * cm, y, str(count))

            y -= self.bar_height + 0.18 * cm


# ==================================================
# Helper functions
# ==================================================

def para(text, style=body_style):
    return Paragraph(str(text), style)


def make_table(data, col_widths=None):
    table = Table(data, colWidths=col_widths, repeatRows=1)

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DARK_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, 0), 9.5),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.35, GRID_GREY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GREY]),
    ]))

    return table


def on_page(canvas, doc):
    canvas.saveState()

    if doc.page > 1:
        canvas.setFillColor(DARK_BLUE)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(1.2 * cm, 0.7 * cm, "QDArchive Part 2 Classification Report")
        canvas.drawRightString(28.5 * cm, 0.7 * cm, f"Page {doc.page}")

        canvas.setStrokeColor(DEEP_GREEN)
        canvas.setLineWidth(0.6)
        canvas.line(1.2 * cm, 1.0 * cm, 28.5 * cm, 1.0 * cm)

    canvas.restoreState()


# ==================================================
# Load database data
# ==================================================

if not DB_PATH.exists():
    raise FileNotFoundError(
        "Could not find db/metadata.db. Run this script from the main project folder."
    )

conn = sqlite3.connect(DB_PATH)

project_type_df = pd.read_sql_query("""
    SELECT
        repository_id,
        project_type,
        COUNT(*) AS count
    FROM projects
    GROUP BY repository_id, project_type
    ORDER BY repository_id, project_type
""", conn)

class_df = pd.read_sql_query("""
    SELECT
        r.repository_id,
        r.project_type,
        r.primary_class,
        r.primary_class_name,
        COUNT(*) AS count
    FROM classification_results r
    WHERE r.classifier_version = ?
      AND r.target_level = 'project'
    GROUP BY
        r.repository_id,
        r.project_type,
        r.primary_class,
        r.primary_class_name
    ORDER BY
        r.repository_id,
        r.project_type,
        count DESC
""", conn, params=(CLASSIFIER_VERSION,))

target_df = pd.read_sql_query("""
    SELECT
        repository_id,
        project_type,
        target_level,
        COUNT(*) AS count
    FROM classification_targets
    GROUP BY repository_id, project_type, target_level
    ORDER BY repository_id, project_type, target_level
""", conn)

file_status_df = pd.read_sql_query("""
    SELECT
        p.repository_id,
        f.file_type,
        f.status,
        COUNT(*) AS count
    FROM files f
    JOIN projects p ON p.id = f.project_id
    GROUP BY p.repository_id, f.file_type, f.status
    ORDER BY p.repository_id, count DESC
""", conn)

totals = pd.read_sql_query("""
    SELECT
        (SELECT COUNT(*) FROM projects) AS total_projects,
        (SELECT COUNT(*) FROM files) AS total_files,
        (SELECT COUNT(*) FROM classification_targets) AS total_targets,
        (SELECT COUNT(*) FROM classification_results) AS total_results
""", conn).iloc[0]

conn.close()


# ==================================================
# Build PDF
# ==================================================

doc = ReportDocTemplate(
    str(OUTPUT_PDF),
    pagesize=PAGE_SIZE,
    rightMargin=1.2 * cm,
    leftMargin=1.2 * cm,
    topMargin=1.2 * cm,
    bottomMargin=1.2 * cm,
)

frame = Frame(
    doc.leftMargin,
    doc.bottomMargin + 0.4 * cm,
    doc.width,
    doc.height - 0.4 * cm,
    id="normal",
)

doc.addPageTemplates([
    PageTemplate(id="ReportPages", frames=[frame], onPage=on_page)
])

story = []


# ==================================================
# Cover page
# ==================================================

story.append(Spacer(1, 0.6 * cm))
story.append(para("QDArchive", title_style))
story.append(para("Part 2 - Classification Report", subtitle_style))
story.append(Spacer(1, 0.5 * cm))

cover_data = [
    [para("Student", cover_label_style), para(STUDENT_NAME, cover_value_style)],
    [para("Student ID", cover_label_style), para(STUDENT_ID, cover_value_style)],
    [para("Institution", cover_label_style), para(INSTITUTION, cover_value_style)],
    [para("Supervisor", cover_label_style), para(SUPERVISOR, cover_value_style)],
    [para("Course", cover_label_style), para(COURSE, cover_value_style)],
    [para("Repositories", cover_label_style), para(REPOSITORIES_TEXT, cover_value_style)],
    [para("Classifier", cover_label_style), para(CLASSIFIER_NAME, cover_value_style)],
    [para("Date", cover_label_style), para(REPORT_DATE, cover_value_style)],
]

cover_table = Table(
    cover_data,
    colWidths=[6 * cm, 14.5 * cm],
    rowHeights=[1.18 * cm] * len(cover_data),
)

cover_table.setStyle(TableStyle([
    ("GRID", (0, 0), (-1, -1), 0.35, GRID_GREY),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("BACKGROUND", (0, 0), (0, -1), SOFT_BLUE),
    ("BACKGROUND", (1, 0), (1, -1), WHITE),
    ("LEFTPADDING", (0, 0), (-1, -1), 14),
    ("RIGHTPADDING", (0, 0), (-1, -1), 14),
    ("TOPPADDING", (0, 0), (-1, -1), 7),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
]))

story.append(cover_table)
story.append(Spacer(1, 0.7 * cm))

note_table = Table(
    [[para(
        "This report summarizes project type assignment, ISIC Rev. 5 classification, repository-wise results, "
        "and limitations for the QDArchive Part 2 workflow.",
        body_style,
    )]],
    colWidths=[20.5 * cm],
)

note_table.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, -1), SOFT_GREEN),
    ("BOX", (0, 0), (-1, -1), 0.5, DEEP_GREEN),
    ("LEFTPADDING", (0, 0), (-1, -1), 12),
    ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ("TOPPADDING", (0, 0), (-1, -1), 8),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
]))

story.append(note_table)
story.append(PageBreak())


# ==================================================
# Table of contents
# ==================================================

story.append(para("Table of Contents", h1_style))

toc = TableOfContents()
toc.levelStyles = [
    ParagraphStyle(
        name="TOCHeading1",
        fontSize=10.5,
        leading=14,
        leftIndent=0,
        firstLineIndent=0,
        textColor=DARK_BLUE,
    ),
    ParagraphStyle(
        name="TOCHeading2",
        fontSize=9.5,
        leading=13,
        leftIndent=18,
        firstLineIndent=0,
        textColor=TEXT_MUTED,
    ),
]

story.append(toc)
story.append(PageBreak())


# ==================================================
# Executive summary
# ==================================================

story.append(para("Executive Summary", h1_style))

story.append(para(
    f"This report presents the Part 2 classification results for the QDArchive seeding project. "
    f"The database contains {int(totals['total_projects'])} projects and {int(totals['total_files'])} file records "
    f"from two repositories: DANS and ICPSR. The goal of this phase was to assign every project a project type "
    f"and to classify QDA_PROJECT and QD_PROJECT entries using the ISIC Rev. 5 division-level taxonomy.",
    body_style,
))

story.append(para(
    f"The project type filtering identified 7 QDA_PROJECT entries and 4570 QD_PROJECT entries in repository_id=5 "
    f"(DANS). These entries were classified at project level and primary-data-file level. In total, "
    f"{int(totals['total_targets'])} classification targets were prepared and {int(totals['total_results'])} "
    f"classification results were stored in the SQLite database.",
    body_style,
))

story.append(para(
    "Repository_id=15 (ICPSR) is present in the database, but its 132 projects were classified as NOT_A_PROJECT. "
    "This happened because the ICPSR acquisition stored metadata-only file records such as restricted or login-required "
    "entries, not concrete primary data file extensions. Therefore, ICPSR rows are included in the final XLSX table, "
    "but they do not have ISIC primary or secondary classes.",
    body_style,
))

summary_table = [
    ["Metric", "Value"],
    ["Total projects", int(totals["total_projects"])],
    ["Total file records", int(totals["total_files"])],
    ["Classification targets", int(totals["total_targets"])],
    ["Classification results", int(totals["total_results"])],
    ["Repositories", "DANS, ICPSR"],
    ["ISIC level used", "Division level"],
]

story.append(make_table(summary_table, col_widths=[7 * cm, 8 * cm]))
story.append(PageBreak())


# ==================================================
# Methodology
# ==================================================

story.append(para("Methodology", h1_style))

story.append(para("Project type assignment", h2_style))
story.append(para(
    "Each project was first assigned to one of four project types using the file extensions stored in the files table. "
    "A project was labelled QDA_PROJECT when at least one qualitative data analysis file extension was found. "
    "If no QDA file was found but at least one primary data extension was present, the project was labelled QD_PROJECT. "
    "Projects with other valid data file types were labelled OTHER_PROJECT. Projects without usable file-type evidence "
    "were labelled NOT_A_PROJECT.",
    body_style,
))

story.append(para("Classification target preparation", h2_style))
story.append(para(
    "For QDA_PROJECT and QD_PROJECT entries, two levels of classification input were created. First, a project-level "
    "target was created using the project title, description, language, keywords, file types, and file names. Second, "
    "a file-level target was created for each primary data file. This followed the requirement to classify both the "
    "project as the sum of its files and each primary data file.",
    body_style,
))

story.append(para("ISIC Rev. 5 taxonomy import", h2_style))
story.append(para(
    "The ISIC Rev. 5 taxonomy was imported from the provided Excel file. The classifier used the hierarchy down to "
    "division level, resulting in 87 division classes. These division descriptions became the reference documents for "
    "automatic classification.",
    body_style,
))

story.append(para("TF-IDF similarity classifier", h2_style))
story.append(para(
    "The classifier used TF-IDF vectorization with English stop-word removal and unigram/bigram features. Each project "
    "or file target was compared against the ISIC division descriptions using cosine similarity. The highest-scoring "
    "division was stored as the primary class. A secondary class was stored only when the second-best match was close "
    "enough to the primary score.",
    body_style,
))

story.append(para("Repository-wise analysis", h2_style))
story.append(para(
    "The results were analyzed by repository and by project type. Histograms and top-20 tables were generated for "
    "classified project-level results. OTHER_PROJECT and NOT_A_PROJECT entries were not classified with ISIC, but they "
    "remain visible in the database and in the XLSX export for completeness.",
    body_style,
))

story.append(PageBreak())


# ==================================================
# Overall project type distribution
# ==================================================

story.append(para("Overall Project Type Distribution", h1_style))

project_type_table = [["Repository", "Repository ID", "Project type", "Count"]]

for _, row in project_type_df.iterrows():
    repo_id = int(row["repository_id"])
    project_type_table.append([
        REPOSITORY_NAMES.get(repo_id, f"Repository {repo_id}"),
        repo_id,
        row["project_type"],
        int(row["count"]),
    ])

story.append(make_table(
    project_type_table,
    col_widths=[5 * cm, 3 * cm, 6 * cm, 3 * cm],
))

story.append(Spacer(1, 0.4 * cm))

story.append(para("Interpretation", h2_style))
story.append(para(
    "The overall distribution shows that repository_id=5 contains the useful classification material for this phase. "
    "Most DANS projects were labelled QD_PROJECT because they contained primary data file extensions. A smaller number "
    "of DANS projects were labelled QDA_PROJECT because they contained QDA file extensions. Repository_id=15 contains "
    "only NOT_A_PROJECT rows because the collected ICPSR file records were metadata-only and did not provide concrete "
    "downloaded primary data file extensions.",
    body_style,
))

story.append(PageBreak())


# ==================================================
# Classification targets
# ==================================================

story.append(para("Classification Target Summary", h1_style))

target_table = [["Repository", "Project type", "Target level", "Count"]]

for _, row in target_df.iterrows():
    repo_id = int(row["repository_id"])
    target_table.append([
        REPOSITORY_NAMES.get(repo_id, f"Repository {repo_id}"),
        row["project_type"],
        row["target_level"],
        int(row["count"]),
    ])

story.append(make_table(
    target_table,
    col_widths=[5 * cm, 6 * cm, 4 * cm, 3 * cm],
))

story.append(Spacer(1, 0.4 * cm))

story.append(para("Interpretation", h2_style))
story.append(para(
    "The target table confirms that the classifier was run on both project-level and file-level targets for "
    "QDA_PROJECT and QD_PROJECT entries. This follows the project instruction to classify the project itself "
    "and each primary data file. Since ICPSR did not contain QDA_PROJECT or QD_PROJECT entries after file-type filtering, "
    "it does not appear in the classification target table.",
    body_style,
))

story.append(PageBreak())


# ==================================================
# Repository analysis sections
# ==================================================

repository_ids = sorted(project_type_df["repository_id"].unique())

for repo_id in repository_ids:
    repo_id = int(repo_id)
    repo_name = REPOSITORY_NAMES.get(repo_id, f"Repository {repo_id}")

    story.append(para(f"Repository Analysis: {repo_name} (repository_id={repo_id})", h1_style))

    repo_project_types = project_type_df[project_type_df["repository_id"] == repo_id]

    repo_table = [["Project type", "Count"]]
    for _, row in repo_project_types.iterrows():
        repo_table.append([row["project_type"], int(row["count"])])

    story.append(para("Repository project type overview", h2_style))
    story.append(make_table(repo_table, col_widths=[7 * cm, 3 * cm]))
    story.append(Spacer(1, 0.4 * cm))

    if repo_id == 5:
        story.append(para("Repository explanation", h2_style))
        story.append(para(
            "DANS is the main repository that produced usable project-level and file-level classification results. "
            "The DANS data contains both QDA_PROJECT and QD_PROJECT entries. Therefore, ISIC classification was applied "
            "to the DANS projects and their primary data files. The large number of QD_PROJECT entries indicates that "
            "many projects contained primary qualitative data files such as text documents, PDFs, spreadsheets, images, "
            "or similar file types.",
            body_style,
        ))

    elif repo_id == 15:
        story.append(para("Repository explanation", h2_style))
        story.append(para(
            "ICPSR is present in the database and in the final XLSX export, but it was not classified with ISIC. "
            "All ICPSR projects were labelled NOT_A_PROJECT because the collected file records were metadata-only. "
            "The file status values show restricted or login-required records, meaning there was not enough file-type "
            "evidence to derive QDA_PROJECT or QD_PROJECT labels.",
            body_style,
        ))

        icpsr_status = file_status_df[file_status_df["repository_id"] == repo_id].head(10)
        if not icpsr_status.empty:
            status_table = [["File type", "Status", "Count"]]
            for _, row in icpsr_status.iterrows():
                status_table.append([
                    row["file_type"],
                    row["status"],
                    int(row["count"]),
                ])

            story.append(para("ICPSR file status evidence", h2_style))
            story.append(make_table(status_table, col_widths=[5 * cm, 7 * cm, 3 * cm]))
            story.append(Spacer(1, 0.4 * cm))

    repo_class_df = class_df[class_df["repository_id"] == repo_id]

    if repo_class_df.empty:
        story.append(para("Classification analysis", h2_style))
        story.append(para(
            "No ISIC primary-class histogram or top-20 class table is shown for this repository because no project "
            "from this repository was eligible for ISIC classification after project type filtering. This should not "
            "be interpreted as missing repository data; it means the projects were outside the classifier scope.",
            body_style,
        ))

        story.append(para("Analysis and comments", h2_style))
        story.append(para(
            "The ICPSR result is important for the final interpretation because it demonstrates the effect of restricted "
            "or metadata-only acquisition. The repository was successfully represented in the database, but the lack of "
            "downloaded files prevented file-extension-based identification of qualitative data projects. For future "
            "work, improving authentication handling or obtaining accessible file metadata from ICPSR would likely change "
            "some of these NOT_A_PROJECT labels into QD_PROJECT or QDA_PROJECT labels.",
            body_style,
        ))

        story.append(PageBreak())
        continue

    for project_type in sorted(repo_class_df["project_type"].unique()):
        group_df = repo_class_df[repo_class_df["project_type"] == project_type].copy()
        group_df = group_df.sort_values("count", ascending=False)
        top20 = group_df.head(20)

        dominant = top20.iloc[0]

        story.append(para(f"Classification analysis for {project_type}", h2_style))
        story.append(para(
            f"The dominant primary class for {repo_name} {project_type} entries is "
            f"{dominant['primary_class']} - {dominant['primary_class_name']} "
            f"with {int(dominant['count'])} project-level classifications.",
            body_style,
        ))

        story.append(BarChartFlowable(
            top20.to_dict("records"),
            title=f"Top 20 primary ISIC classes: {repo_name} - {project_type}",
        ))

        story.append(Spacer(1, 0.5 * cm))

        top20_table = [["Rank", "Primary class", "Class name", "Count"]]

        for rank, (_, row) in enumerate(top20.iterrows(), start=1):
            top20_table.append([
                rank,
                row["primary_class"],
                para(row["primary_class_name"], small_style),
                int(row["count"]),
            ])

        story.append(para("Rank-ordered top 20 classes", h2_style))
        story.append(make_table(
            top20_table,
            col_widths=[1.5 * cm, 3 * cm, 14 * cm, 2.2 * cm],
        ))

        story.append(Spacer(1, 0.4 * cm))

        story.append(para("Analysis and comments", h2_style))

        if project_type == "QDA_PROJECT":
            story.append(para(
                "The QDA_PROJECT group is very small, with only seven projects. Because of this small sample size, "
                "the dominant class should be interpreted carefully. A small number of projects can strongly influence "
                "the class distribution. The result is still useful because it verifies that QDA projects can be detected "
                "and classified separately from ordinary qualitative data projects.",
                body_style,
            ))

        elif project_type == "QD_PROJECT":
            story.append(para(
                "The QD_PROJECT group is much larger and therefore gives a broader view of the repository content. "
                "The dominant classes reflect the textual signals available in project titles, descriptions, keywords, "
                "and file names. Since many records contain generic metadata or file names, the classifier results should "
                "be interpreted as automatic first-pass labels rather than manually verified labels.",
                body_style,
            ))

        story.append(para(
            "The TF-IDF method is transparent and reproducible, but it has limitations. It does not understand context "
            "as deeply as a supervised or embedding-based model. It assigns classes based on textual similarity between "
            "project metadata and ISIC division descriptions. Therefore, projects with short descriptions, missing "
            "keywords, or generic file names may receive weak or unexpected ISIC matches.",
            body_style,
        ))

        story.append(PageBreak())


# ==================================================
# Limitations and conclusion
# ==================================================

story.append(para("Limitations", h1_style))

limitations_table = [
    ["Limitation", "Explanation"],
    [
        "Low metadata detail",
        para("Some projects contain short or generic titles, descriptions, keywords, or file names. This reduces classifier confidence.", small_style),
    ],
    [
        "Metadata-only ICPSR records",
        para("ICPSR records were present, but they were restricted or login-required and therefore did not provide usable file-type evidence.", small_style),
    ],
    [
        "Automatic classification",
        para("The ISIC labels were produced automatically and were not manually validated.", small_style),
    ],
    [
        "TF-IDF matching",
        para("TF-IDF gives reproducible similarity scores, but it does not capture deep semantic meaning.", small_style),
    ],
    [
        "Secondary classes",
        para("Secondary classes were stored only when the second-best class was close enough to the primary class.", small_style),
    ],
]

story.append(make_table(limitations_table, col_widths=[6 * cm, 16 * cm]))

story.append(Spacer(1, 0.5 * cm))

story.append(para("Conclusion", h1_style))
story.append(para(
    "The Part 2 workflow successfully added project type labels, imported the ISIC Rev. 5 taxonomy, created "
    "classification targets, ran a division-level classifier, exported the required XLSX table, and created the final "
    "classification database. The DANS repository produced both QDA_PROJECT and QD_PROJECT entries and was classified "
    "with ISIC. The ICPSR repository remained visible in the outputs but was not classified because all its projects "
    "were labelled NOT_A_PROJECT based on available file-type evidence.",
    body_style,
))

story.append(para(
    "Overall, the result provides a reproducible first-pass classification pipeline for QDArchive seeding. The database "
    "and exported files can be used for further analysis, manual validation, and future improvement of the classifier.",
    body_style,
))


doc.multiBuild(story)

print(f"Created improved PDF report: {OUTPUT_PDF}")
print("Updated Step 8 finished successfully.")