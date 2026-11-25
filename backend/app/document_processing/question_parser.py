import re
from typing import Any


def extract_question_paper_context(extracted_text: str) -> str:
    """
    Preserve instructions, descriptions and all detected tables,
    including tables appended after the Questions section.
    """

    text = extracted_text.replace("\r\n", "\n").replace("\r", "\n")

    # Extract every structured table block from the document.
    table_blocks = re.findall(
        r"(?ms)^\[\[TABLE_START:\d+\]\]\s*\n.*?^\[\[TABLE_END\]\]\s*$",
        text,
    )

    # Remove table blocks before locating the Questions section.
    text_without_tables = re.sub(
        r"(?ms)^\[\[TABLE_START:\d+\]\]\s*\n.*?^\[\[TABLE_END\]\]\s*$",
        "",
        text,
    )

    # Locate the Questions heading.
    section_match = re.search(
        r"(?im)^\s*(?:SQL\s+)?Questions\s*:?\s*$",
        text_without_tables,
    )

    if not section_match:
        raise ValueError(
            "Could not identify the Questions section in the document."
        )

    # Preserve the instructions and reference material.
    context = text_without_tables[:section_match.start()].strip()

    # Append all structured tables, regardless of their original position.
    if table_blocks:
        context += "\n\n" + "\n\n".join(table_blocks)

    if not context:
        raise ValueError(
            "No instructions or database context found in the document."
        )

    return context


def parse_questions(extracted_text: str) -> list[dict[str, Any]]:
    """
    Parse numbered questions from extracted question paper text.

    Deterministic parsing only.
    No AI generation or rewriting.
    """

    text = extracted_text.replace("\r\n", "\n").replace("\r", "\n")

    # Locate the Questions section.
    section_match = re.search(
        r"(?im)^\s*(?:SQL\s+)?Questions\s*:?\s*$",
        text,
    )

    if not section_match:
        raise ValueError(
            "Could not identify the Questions section in the document."
        )

    questions_text = text[section_match.end():]

    # Remove page headers, footers and end markers.
    questions_text = re.sub(
        r"(?im)^\s*\[Page\s+\d+\]\s*$",
        "",
        questions_text,
    )

    questions_text = re.sub(
        r"(?im)^\s*Page\s+\d+\s*$",
        "",
        questions_text,
    )

    questions_text = re.sub(
        r"(?im)^\s*End of Question Paper\s*$",
        "",
        questions_text,
    )

    # Remove repeated document title/footer.
    questions_text = re.sub(
        r"(?im)^\s*SQL Query Review\s*[—–-]\s*Company Database\s*$",
        "",
        questions_text,
    )

    # Identify numbered question boundaries.
    pattern = r"(?m)^\s*(\d+)\.\s+"
    matches = list(re.finditer(pattern, questions_text))

    if not matches:
        raise ValueError(
            "No numbered questions were found in the document."
        )

    parsed_questions = []

    for index, match in enumerate(matches):
        question_number = int(match.group(1))

        start = match.end()

        end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(questions_text)
        )

        question_text = questions_text[start:end].strip()

        # Normalize whitespace.
        question_text = re.sub(
            r"\s+",
            " ",
            question_text,
        ).strip()

        # Extract marks.
        marks_match = re.search(
            r"\((\d+(?:\.\d+)?)\s*marks?\)",
            question_text,
            re.IGNORECASE,
        )

        marks = (
            float(marks_match.group(1))
            if marks_match
            else None
        )

        # Remove marks from question text.
        if marks_match:
            question_text = (
                question_text[:marks_match.start()]
                + question_text[marks_match.end():]
            ).strip()

        # Clean spacing before punctuation.
        question_text = re.sub(
            r"\s+([:;,.])",
            r"\1",
            question_text,
        )

        if not question_text:
            continue

        parsed_questions.append({
            "question_id": f"imported_q{question_number}",
            "question_number": question_number,
            "question": question_text,
            "question_type": "subjective",
            "options": {},
            "marks": marks,
        })

    if not parsed_questions:
        raise ValueError(
            "Question parsing did not produce any valid questions."
        )

    return parsed_questions