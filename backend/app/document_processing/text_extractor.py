import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
from docx import Document
from pptx import Presentation


class DocumentExtractionError(Exception):
    """Raised when text extraction fails."""

def extract_pdf(file_path: Path) -> str:
    """Extract PDF text while preserving detected table structures."""

    text_parts = []

    try:
        with fitz.open(file_path) as pdf:
            for page_number, page in enumerate(pdf, start=1):

                page_parts = [
                    f"\n[Page {page_number}]\n"
                ]

                # Detect tables on the page.
                detected_tables = []

                if hasattr(page, "find_tables"):
                    try:
                        table_finder = page.find_tables()
                        detected_tables = table_finder.tables
                    except Exception:
                        detected_tables = []

                # Extract normal page text.
                page_text = page.get_text("text").strip()

                if page_text:
                    page_parts.append(page_text)

                # Extract every detected table.
                for table_number, table in enumerate(
                    detected_tables,
                    start=1,
                ):
                    extracted_rows = table.extract()
                    print("\n========== EXTRACTED TABLE ==========")
                    for row in extracted_rows:
                        print(row)
                    print("=====================================")

                    if not extracted_rows:
                        continue

                    page_parts.append(
                        f"\n[[TABLE_START:{table_number}]]"
                    )

                    for row in extracted_rows:
                        cells = [
                            str(cell).strip() if cell is not None else ""
                            for cell in row
                        ]

                        page_parts.append(
                            " | ".join(cells)
                        )

                    page_parts.append("[[TABLE_END]]")

                text_parts.append("\n".join(page_parts))

    except Exception as error:
        raise DocumentExtractionError(
            f"Could not extract PDF text: {error}"
        ) from error

    return "\n".join(text_parts)


def extract_docx(file_path: Path) -> str:
    """Extract text from a DOCX file."""

    text_parts = []

    try:
        document = Document(file_path)

        for paragraph in document.paragraphs:
            text = paragraph.text.strip()

            if text:
                text_parts.append(text)

        # Extract text from tables as well.
        for table in document.tables:
            for row in table.rows:
                cells = [
                    cell.text.strip()
                    for cell in row.cells
                    if cell.text.strip()
                ]

                if cells:
                    text_parts.append(" | ".join(cells))

    except Exception as error:
        raise DocumentExtractionError(
            f"Could not extract DOCX text: {error}"
        ) from error

    return "\n".join(text_parts)

def extract_doc(file_path: Path) -> str:
    """Extract text from a legacy Microsoft Word DOC file."""

    antiword = shutil.which("antiword")

    if antiword:
        try:
            result = subprocess.run(
                [antiword, str(file_path)],
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
            )

            text = result.stdout.strip()

            if text:
                return text

        except subprocess.SubprocessError as error:
            raise DocumentExtractionError(
                f"Could not extract DOC file: {error}"
            ) from error

    # Fallback: Convert DOC to DOCX using LibreOffice.
    soffice = shutil.which("soffice")

    if soffice:
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                subprocess.run(
                    [
                        soffice,
                        "--headless",
                        "--convert-to",
                        "docx",
                        "--outdir",
                        temp_dir,
                        str(file_path),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=True,
                )

                converted_file = (
                    Path(temp_dir) / f"{file_path.stem}.docx"
                )

                if converted_file.exists():
                    return extract_docx(converted_file)

        except subprocess.SubprocessError as error:
            raise DocumentExtractionError(
                f"Could not convert DOC file: {error}"
            ) from error

    raise DocumentExtractionError(
        "Legacy DOC extraction requires Antiword or LibreOffice. "
        "Please install one of these tools."
    )

def extract_pptx(file_path: Path) -> str:
    """Extract text from a PowerPoint presentation."""

    text_parts = []

    try:
        presentation = Presentation(file_path)

        for slide_number, slide in enumerate(
            presentation.slides,
            start=1,
        ):
            slide_parts = []

            for shape in slide.shapes:

                # Extract normal text.
                if shape.has_text_frame:
                    text = shape.text.strip()

                    if text:
                        slide_parts.append(text)

                # Extract text from tables.
                if shape.has_table:
                    for row in shape.table.rows:
                        cells = [
                            cell.text.strip()
                            for cell in row.cells
                            if cell.text.strip()
                        ]

                        if cells:
                            slide_parts.append(" | ".join(cells))

            if slide_parts:
                text_parts.append(
                    f"\n[Slide {slide_number}]\n"
                    + "\n".join(slide_parts)
                )

    except Exception as error:
        raise DocumentExtractionError(
            f"Could not extract PPTX text: {error}"
        ) from error

    return "\n".join(text_parts)


def extract_txt(file_path: Path) -> str:
    """Extract text from a TXT file."""

    try:
        return file_path.read_text(
            encoding="utf-8-sig"
        ).strip()

    except UnicodeDecodeError as error:
        raise DocumentExtractionError(
            "TXT file must use UTF-8 encoding."
        ) from error

    except OSError as error:
        raise DocumentExtractionError(
            f"Could not read TXT file: {error}"
        ) from error


def extract_text(file_path: str | Path) -> str:
    """
    Main extraction function.

    Automatically identifies the file format and
    extracts its textual content.
    """

    path = Path(file_path)

    if not path.exists():
        raise DocumentExtractionError(
            f"File does not exist: {path}"
        )

    if not path.is_file():
        raise DocumentExtractionError(
            "The supplied path is not a file."
        )

    extension = path.suffix.lower()

    extractors = {
        ".pdf": extract_pdf,
        ".doc": extract_doc,
        ".docx": extract_docx,
        ".pptx": extract_pptx,
        ".txt": extract_txt,
    }

    extractor = extractors.get(extension)

    if extractor is None:
        raise DocumentExtractionError(
            f"Unsupported file format: {extension}"
        )

    extracted_text = extractor(path)

    if not extracted_text.strip():
        raise DocumentExtractionError(
            "No readable text was found in the document. "
            "The document may contain only scanned images."
        )

    return extracted_text