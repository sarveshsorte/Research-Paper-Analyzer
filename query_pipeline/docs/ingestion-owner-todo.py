from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


output = "docs/data-ingestion-owner-todo.pdf"
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(
    name="TitleCenter",
    parent=styles["Title"],
    alignment=TA_CENTER,
    fontSize=20,
    leading=24,
    spaceAfter=18,
))
styles.add(ParagraphStyle(
    name="Section",
    parent=styles["Heading2"],
    fontSize=14,
    leading=18,
    textColor=colors.HexColor("#17365D"),
    spaceBefore=12,
    spaceAfter=8,
))
styles.add(ParagraphStyle(
    name="Small",
    parent=styles["BodyText"],
    fontSize=9,
    leading=12,
))


def bullet(text: str) -> Paragraph:
    return Paragraph(f"&#9633; {text}", styles["BodyText"])


def code(text: str) -> Paragraph:
    return Paragraph(f"<font name='Courier'>{text}</font>", styles["Small"])


story = [
    Paragraph("ResearchLens Data Ingestion Handoff", styles["TitleCenter"]),
    Paragraph(
        "To-do checklist for the teammate responsible for document ingestion, "
        "indexing, and production data connections.",
        styles["BodyText"],
    ),
    Spacer(1, 12),
    Table(
        [
            ["Query pipeline status", "Implemented and tested with fake providers"],
            ["Ingestion status", "Must be connected and verified"],
            ["Current test result", "12 tests passed"],
            ["Primary contract", "docs/ingestion-contract.md"],
        ],
        colWidths=[1.6 * inch, 4.8 * inch],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#D9EAF7")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("PADDING", (0, 0), (-1, -1), 6),
        ]),
    ),
    Paragraph("1. Repository and database integration", styles["Section"]),
    bullet("Implement the real paper repository and return only papers whose status is ready."),
    bullet("Implement the real chunk repository, including indexed_papers(workspace_id, paper_ids)."),
    bullet("Implement workspace membership checks for authenticated users."),
    bullet("Replace the temporary in-memory repositories in backend/app/dependencies.py."),
    bullet("Preserve workspace isolation in every repository query."),
    Paragraph("2. Document processing and chunk contract", styles["Section"]),
    bullet("Preserve exact chunk text; do not normalize away meaningful content."),
    bullet("Generate stable unique chunk_id values."),
    bullet("Store workspace_id, paper_id, paper_title, section, content_type, and chunk_index."),
    bullet("Use one-based inclusive page_start and page_end values."),
    bullet("Generate content_hash from the canonical chunk text."),
    bullet("Mark a paper queryable only after metadata, vectors, and sparse index entries are complete."),
    Paragraph("3. Qdrant dense-index integration", styles["Section"]),
    bullet("Use the configured QDRANT_COLLECTION, normally paper_chunks."),
    bullet("Use cosine distance and the exact EMBEDDING_DIMENSION used by the query service."),
    bullet("Store the required payload fields from docs/ingestion-contract.md."),
    bullet("Ensure payload.chunk_id is canonical even if the Qdrant point ID is a UUID."),
    bullet("Verify filtering by workspace_id and selected paper_id values."),
    bullet("Run a retrieval test proving page and metadata lineage is preserved."),
    Paragraph("4. BM25 / sparse retrieval integration", styles["Section"]),
    bullet("Build or connect the BM25 index using the exact chunk text."),
    bullet("Return the same chunk_id values as the dense index."),
    bullet("Preserve workspace_id, paper_id, page, section, and content_hash metadata."),
    bullet("Apply the same workspace, paper, page, section, and content-type filters."),
    bullet("Test dense-only, sparse-only, and hybrid retrieval cases."),
    PageBreak(),
    Paragraph("5. Model and environment configuration", styles["Section"]),
    bullet("Confirm the ingestion embedding model matches EMBEDDING_MODEL."),
    bullet("Confirm the vector size matches EMBEDDING_DIMENSION, currently 2048."),
    bullet("Do not copy the developer's .env file or API keys."),
    bullet("Create a private local .env from .env.example."),
    bullet("Set USE_FAKE_PROVIDERS=true while testing without live services."),
    bullet("Before live generation, configure a valid NVIDIA_API_KEY and NVIDIA_MODEL."),
    code("NVIDIA_API_KEY=<private-key>"),
    code("NVIDIA_MODEL=nvidia/nemotron-3-ultra-550b-a55b"),
    code("USE_FAKE_PROVIDERS=false"),
    Paragraph("6. Replace provider wiring", styles["Section"]),
    bullet("Connect real paper, chunk, and workspace repositories."),
    bullet("Connect the BM25 provider and optional reranker."),
    bullet("Keep provider failures explicit; do not silently fall back to fake data."),
    bullet("Verify timeout, authentication, rate-limit, and malformed-response behavior."),
    Paragraph("7. Required acceptance tests", styles["Section"]),
    bullet("A query cannot access papers from another workspace."),
    bullet("A selected paper that is not ready returns paper_not_ready."),
    bullet("A ready paper without indexed chunks is rejected."),
    bullet("Dense retrieval returns candidates with complete citation metadata."),
    bullet("Sparse and dense retrieval resolve to the same chunk IDs."),
    bullet("Page filters and section filters are enforced by both retrieval paths."),
    bullet("A missing or invalid generation response returns generation_failed."),
    bullet("A complete query returns controlled source IDs such as S1 and S2."),
    bullet("Run pytest -q from query_pipeline and python3 -m compileall -q backend database query_pipeline."),
    Paragraph("8. Definition of done", styles["Section"]),
    bullet("All repository protocols are backed by real ingestion implementations."),
    bullet("Qdrant and BM25 contain the same indexed chunk metadata."),
    bullet("Embedding model, dimension, collection, and distance are verified."),
    bullet("Workspace authorization is tested with real identity data."),
    bullet("End-to-end query succeeds against a real indexed paper."),
    bullet("No secrets are committed, shared, or placed in documentation."),
    bullet("The final integration details are recorded in docs/ingestion-contract.md."),
    Spacer(1, 14),
    Paragraph(
        "<b>Handoff boundary:</b> The query pipeline is complete on the provider-independent "
        "fake path. This checklist covers the remaining ingestion and production integration "
        "work required before declaring the complete system production-ready.",
        styles["Small"],
    ),
]

doc = SimpleDocTemplate(
    output,
    pagesize=letter,
    rightMargin=0.65 * inch,
    leftMargin=0.65 * inch,
    topMargin=0.6 * inch,
    bottomMargin=0.6 * inch,
    title="ResearchLens Data Ingestion Handoff",
)
doc.build(story)
