from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from backend.app.agents.exam_session_agent.exam_session_agent import ExamSessionAgent
from backend.app.graph.exam_graph import evaluation_node, exam_graph
from backend.app.schemas.exam_request import ExamRequest
from backend.app.schemas.exam_session import ExamSession, ExamSessionStatus

from copy import deepcopy
# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Online Course Examination System",
    description="Exam generation, session management, authentication, and automated evaluation.",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

session_agent = ExamSessionAgent()
sessions: dict[str, dict[str, Any]] = {}
sessions_lock = Lock()

AUTH_DB = Path(__file__).resolve().parent / "auth_users.db"
SECRET_FILE = Path(__file__).resolve().parent / ".auth_secret"
AUTH_SECRET = os.getenv("AUTH_SECRET_KEY")

if not AUTH_SECRET:
    if not SECRET_FILE.exists():
        SECRET_FILE.write_text(secrets.token_hex(32), encoding="utf-8")
    AUTH_SECRET = SECRET_FILE.read_text(encoding="utf-8").strip()

bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Authentication models and helpers
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=8, max_length=128)
    name: str = Field(..., min_length=1, max_length=120)
    roll_number: int = Field(..., ge=1)
    usn: str = Field(..., min_length=1, max_length=50)
    division: str = Field(..., min_length=1, max_length=30)
    role: str = Field(default="student", pattern="^(student|teacher)$")


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=1, max_length=128)


class AnswerRequest(BaseModel):
    question_id: str = Field(..., min_length=1)
    answer: str = Field(default="", max_length=100_000)


def init_auth_db() -> None:
    AUTH_DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(AUTH_DB) as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                name TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('student', 'teacher')),
                roll_number INTEGER,
                usn TEXT,
                division TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        db.commit()


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, 310_000
    )
    return f"{salt.hex()}:{digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_hex, expected_digest = stored_hash.split(":", 1)
        actual_digest = hash_password(
            password, bytes.fromhex(salt_hex)
        ).split(":", 1)[1]
        return hmac.compare_digest(actual_digest, expected_digest)
    except (ValueError, TypeError):
        return False


def create_token(user: dict[str, Any]) -> str:
    payload = {
        "sub": user["email"],
        "role": user["role"],
        "exp": int(time.time()) + 8 * 60 * 60,
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    signature = hmac.new(
        AUTH_SECRET.encode("utf-8"),
        encoded.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    return f"{encoded}.{signature}"


def safe_user(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "role": row["role"],
        "roll_number": row["roll_number"],
        "usn": row["usn"],
        "division": row["division"],
    }


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Please log in to continue")

    try:
        encoded, supplied_signature = credentials.credentials.split(".", 1)
        expected_signature = hmac.new(
            AUTH_SECRET.encode("utf-8"),
            encoded.encode("ascii"),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise ValueError("Invalid token signature")

        padded = encoded + "=" * (-len(encoded) % 4)
        payload = json.loads(
            base64.urlsafe_b64decode(padded.encode("ascii"))
        )

        if int(payload["exp"]) <= int(time.time()):
            raise ValueError("Token expired")

        email = str(payload["sub"]).lower()
        token_role = str(payload["role"])

        with sqlite3.connect(AUTH_DB) as db:
            db.row_factory = sqlite3.Row
            row = db.execute(
                """
                SELECT id, email, name, role, roll_number, usn, division
                FROM users WHERE email = ?
                """,
                (email,),
            ).fetchone()

        if row is None or row["role"] != token_role:
            raise ValueError("User or role no longer valid")

        return safe_user(row)

    except (
        ValueError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
        UnicodeDecodeError,
    ):
        raise HTTPException(
            status_code=401, detail="Invalid or expired login session"
        )


def require_role(*allowed_roles: str):
    def dependency(user: dict[str, Any] = Depends(get_current_user)):
        if user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail="Your account does not have permission for this action",
            )
        return user

    return dependency


init_auth_db()


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def public_session(state: dict[str, Any]) -> dict[str, Any]:
    """Return student-safe exam data; never expose answer keys."""
    session = state.get("exam_session") or {}
    questions = state.get("student_questions") or []

    return {
        "session_id": session.get("session_id"),
        "exam_id": session.get("exam_id"),
        "status": session.get("status"),
        "started_at": session.get("started_at"),
        "ends_at": session.get("ends_at"),
        "total_questions": session.get("total_questions", len(questions)),
        "answered_questions": session.get("answered_questions", 0),
        "questions": questions,
    }


def session_question_ids(state: dict[str, Any]) -> set[str]:
    """Accept IDs from the student-safe question list, with a fallback."""
    questions = state.get("student_questions") or state.get("questions") or []
    return {
        str(question.get("question_id") or question.get("id"))
        for question in questions
        if question.get("question_id") or question.get("id")
    }


def load_session(session_id: str) -> dict[str, Any]:
    state = sessions.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Exam session not found")
    return state


# ---------------------------------------------------------------------------
# Basic endpoints
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    return {
        "message": "Online Course Examination API",
        "docs": "/docs",
        "health": "/api/health",
    }


@app.get("/api/health")
def health():
    return {"status": "ok", "api": "running"}


# ---------------------------------------------------------------------------
# Authentication endpoints
# ---------------------------------------------------------------------------

@app.post("/api/auth/register", status_code=201)
def register(request: RegisterRequest):
    email = request.email.lower().strip()
    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        raise HTTPException(status_code=422, detail="Enter a valid email address")

    try:
        with sqlite3.connect(AUTH_DB) as db:
            db.execute(
                """
                INSERT INTO users
                    (email, password_hash, name, role, roll_number, usn, division)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    email,
                    hash_password(request.password),
                    request.name.strip(),
                    request.role,
                    request.roll_number if request.role == "student" else None,
                    request.usn.strip() if request.role == "student" else None,
                    request.division.strip() if request.role == "student" else None,
                ),
            )
            db.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists",
        )

    return {"message": "Account created successfully. Please log in."}


@app.post("/api/auth/login")
def login(request: LoginRequest):
    email = request.email.lower().strip()
    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        raise HTTPException(status_code=422, detail="Enter a valid email address")

    with sqlite3.connect(AUTH_DB) as db:
        db.row_factory = sqlite3.Row
        row = db.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()

    if row is None or not verify_password(
        request.password, row["password_hash"]
    ):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    user = safe_user(row)
    return {
        "access_token": create_token(user),
        "token_type": "bearer",
        "user": user,
    }


@app.get("/api/auth/me")
def me(user: dict[str, Any] = Depends(get_current_user)):
    return user


# ---------------------------------------------------------------------------
# Exam endpoints
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Exam endpoints
# ---------------------------------------------------------------------------

def _same_division(a: Any, b: Any) -> bool:
    return str(a or "").strip().upper() == str(b or "").strip().upper()


def _student_attempt_for_assignment(
    assignment_id: str,
    student_email: str,
) -> tuple[str, dict[str, Any]] | None:
    for sid, state in sessions.items():
        if (
            state.get("_assignment_id") == assignment_id
            and state.get("_student_email") == student_email
        ):
            return sid, state
    return None


def _can_access_attempt(state: dict[str, Any], user: dict[str, Any]) -> bool:
    if user["role"] == "teacher":
        return state.get("_owner_email") == user["email"]

    return (
        state.get("_student_email") == user["email"]
        and _same_division(
            state.get("_target_division"),
            user.get("division"),
        )
    )


@app.post("/api/exams")
def generate_exam(
    request: ExamRequest,
    user: dict[str, Any] = Depends(require_role("teacher")),
):
    """
    Generate ONE examination for an entire division.

    The graph still receives a Student object because the existing graph/schema
    requires it, but that student is only used as generation context.
    Assignment/access is division based.
    """
    try:
        from backend.app.graph.exam_graph import create_exam_state

        target_division = str(request.student.division).strip()
        if not target_division:
            raise HTTPException(
                status_code=422,
                detail="Target division is required",
            )

        initial_state = create_exam_state(request)
        result = exam_graph.invoke(initial_state)

        if result.get("current_stage") == "error":
            raise HTTPException(
                status_code=500,
                detail={
                    "message": "Exam workflow failed",
                    "errors": result.get("errors", []),
                },
            )

        session_data = result.get("exam_session") or {}
        assignment_id = session_data.get("session_id")

        if not assignment_id:
            raise HTTPException(
                status_code=500,
                detail="Workflow did not create an examination",
            )

        # IMPORTANT:
        # This object is now the DIVISION ASSIGNMENT / TEMPLATE.
        # Students do not answer directly into this session.
        result["_is_assignment"] = True
        result["_assignment_id"] = assignment_id
        result["_owner_email"] = user["email"]
        result["_owner_role"] = "teacher"
        result["_target_division"] = target_division

        result["_subject"] = getattr(request, "subject", None)
        result["_topic"] = getattr(request, "topic", None)
        result["_difficulty"] = getattr(request, "difficulty", None)

        # Remove old single-student ownership semantics.
        result.pop("_student_roll_number", None)
        result.pop("_student_usn", None)
        result.pop("_student_name", None)

        with sessions_lock:
            sessions[assignment_id] = result

        response = public_session(result)
        response.update({
            "session_id": assignment_id,
            "assignment_id": assignment_id,
            "division": target_division,
            "subject": result.get("_subject"),
            "topic": result.get("_topic"),
            "difficulty": result.get("_difficulty"),
            "status": "assigned",
            "is_assignment": True,
        })

        return {
            "message": f"Exam generated for Division {target_division}",
            **response,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Exam generation failed: {exc}",
        ) from exc


@app.get("/api/teacher/exams")
def list_teacher_exams(
    user: dict[str, Any] = Depends(require_role("teacher")),
):
    with sessions_lock:
        exams = []

        for state in sessions.values():
            if not state.get("_is_assignment"):
                continue

            if state.get("_owner_email") != user["email"]:
                continue

            assignment_id = state.get("_assignment_id")

            attempts = [
                attempt
                for attempt in sessions.values()
                if attempt.get("_assignment_id") == assignment_id
                and not attempt.get("_is_assignment")
            ]

            submitted = 0
            in_progress = 0

            for attempt in attempts:
                session = attempt.get("exam_session") or {}
                status = str(session.get("status") or "")

                if status in ("submitted", "evaluated", "completed"):
                    submitted += 1
                elif status == "in_progress":
                    in_progress += 1

            exam = public_session(state)

            exam.update({
                "session_id": assignment_id,
                "assignment_id": assignment_id,
                "division": state.get("_target_division"),
                "subject": state.get("_subject"),
                "topic": state.get("_topic"),
                "difficulty": state.get("_difficulty"),
                "status": "assigned",
                "is_assignment": True,
                "attempt_count": len(attempts),
                "submitted_count": submitted,
                "in_progress_count": in_progress,
            })

            exams.append(exam)

        return {"exams": exams}


@app.get("/api/student/exams")
def list_student_exams(
    user: dict[str, Any] = Depends(require_role("student")),
):
    student_division = user.get("division")

    if not student_division:
        return {"exams": []}

    with sessions_lock:
        exams = []

        for state in sessions.values():
            if not state.get("_is_assignment"):
                continue

            if not _same_division(
                state.get("_target_division"),
                student_division,
            ):
                continue

            assignment_id = state.get("_assignment_id")

            existing = _student_attempt_for_assignment(
                assignment_id,
                user["email"],
            )

            if existing:
                attempt_id, attempt_state = existing
                exam = public_session(attempt_state)

                exam.update({
                    "session_id": attempt_id,
                    "assignment_id": assignment_id,
                    "division": state.get("_target_division"),
                    "subject": state.get("_subject"),
                    "topic": state.get("_topic"),
                    "difficulty": state.get("_difficulty"),
                    "has_attempt": True,
                })
            else:
                # Until the student starts, expose the assignment id.
                # GET /api/exams/{id} will create their private attempt.
                exam = public_session(state)

                exam.update({
                    "session_id": assignment_id,
                    "assignment_id": assignment_id,
                    "division": state.get("_target_division"),
                    "subject": state.get("_subject"),
                    "topic": state.get("_topic"),
                    "difficulty": state.get("_difficulty"),
                    "status": "not_started",
                    "answered_questions": 0,
                    "has_attempt": False,
                })

            exams.append(exam)

        return {"exams": exams}


def _create_student_attempt(
    assignment: dict[str, Any],
    user: dict[str, Any],
) -> dict[str, Any]:
    """
    Create an independent ExamSession for ONE student from the division
    assignment. Questions are reused; answers/session state are NOT shared.
    """
    assignment_id = assignment["_assignment_id"]

    existing = _student_attempt_for_assignment(
        assignment_id,
        user["email"],
    )

    if existing:
        return existing[1]

    questions = (
        assignment.get("questions")
        or assignment.get("validated_questions")
        or []
    )

    if not questions:
        raise HTTPException(
            status_code=500,
            detail="Generated examination contains no questions",
        )

    student_id = str(
        user.get("usn")
        or user.get("roll_number")
        or user["email"]
    )

    # Create a completely independent session.
    new_session = session_agent.create_session(
        exam_id=str(
            (assignment.get("exam_session") or {}).get("exam_id")
            or assignment_id
        ),
        student_id=student_id,
        questions=questions,
        duration_minutes=30,
    )

    new_session = session_agent.start_session(new_session)

    attempt = deepcopy(assignment)

    attempt["_is_assignment"] = False
    attempt["_assignment_id"] = assignment_id
    attempt["_student_email"] = user["email"]
    attempt["_student_roll_number"] = user.get("roll_number")
    attempt["_student_usn"] = user.get("usn")
    attempt["_student_name"] = user.get("name")
    attempt["_target_division"] = user.get("division")

    attempt["exam_session"] = new_session.model_dump(mode="json")
    attempt["answers"] = []
    attempt["evaluation_results"] = []
    attempt["final_result"] = None

    # Rebuild safe questions from the full generated questions.
    attempt["student_questions"] = session_agent.get_questions(
        new_session,
        questions,
    )

    sessions[new_session.session_id] = attempt

    return attempt


@app.get("/api/exams/{session_id}")
def get_exam(
    session_id: str,
    user: dict[str, Any] = Depends(get_current_user),
):
    with sessions_lock:
        state = load_session(session_id)

        # Teacher may inspect their assignment.
        if user["role"] == "teacher":
            if state.get("_owner_email") != user["email"]:
                raise HTTPException(
                    status_code=403,
                    detail="You cannot access this examination",
                )

            return {
                **public_session(state),
                "division": state.get("_target_division"),
                "subject": state.get("_subject"),
                "topic": state.get("_topic"),
            }

        # STUDENT OPENING A DIVISION ASSIGNMENT:
        # create/reuse their own private attempt.
        if state.get("_is_assignment"):
            if not _same_division(
                state.get("_target_division"),
                user.get("division"),
            ):
                raise HTTPException(
                    status_code=403,
                    detail="This examination is assigned to another division",
                )

            state = _create_student_attempt(state, user)

        elif not _can_access_attempt(state, user):
            raise HTTPException(
                status_code=403,
                detail="This examination is not assigned to your account",
            )

        return public_session(state)


@app.post("/api/exams/{session_id}/answers")
def save_answer(
    session_id: str,
    request: AnswerRequest,
    user: dict[str, Any] = Depends(require_role("student")),
):
    with sessions_lock:
        state = load_session(session_id)

        if state.get("_is_assignment"):
            raise HTTPException(
                status_code=409,
                detail="Start the examination before answering",
            )

        if not _can_access_attempt(state, user):
            raise HTTPException(
                status_code=403,
                detail="This examination is not assigned to your account",
            )

        try:
            session = ExamSession.model_validate(
                state["exam_session"]
            )

            if session.status != ExamSessionStatus.IN_PROGRESS:
                raise HTTPException(
                    status_code=409,
                    detail="This exam is not accepting answers",
                )

            if request.question_id not in session_question_ids(state):
                raise HTTPException(
                    status_code=404,
                    detail="Question not found in this examination",
                )

            session_agent.submit_answer(
                session=session,
                question_id=request.question_id,
                answer=request.answer,
            )

            state["exam_session"] = session.model_dump(mode="json")

            state["answers"] = [
                answer.model_dump(mode="json")
                for answer in session.answers.values()
            ]

            sessions[session_id] = state

            return {
                "message": "Answer saved",
                "answered_questions": session.answered_questions,
                "total_questions": session.total_questions,
            }

        except HTTPException:
            raise
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=str(exc),
            ) from exc


@app.post("/api/exams/{session_id}/submit")
def submit_exam(
    session_id: str,
    user: dict[str, Any] = Depends(require_role("student")),
):
    with sessions_lock:
        state = load_session(session_id)

        if state.get("_is_assignment"):
            raise HTTPException(
                status_code=409,
                detail="Start the examination before submitting",
            )

        if not _can_access_attempt(state, user):
            raise HTTPException(
                status_code=403,
                detail="This examination is not assigned to your account",
            )

        try:
            session = ExamSession.model_validate(
                state["exam_session"]
            )

            if session.status != ExamSessionStatus.IN_PROGRESS:
                raise HTTPException(
                    status_code=409,
                    detail="This examination has already been submitted",
                )

            # Locks the attempt BEFORE evaluation.
            session = session_agent.submit_session(session)

            state["exam_session"] = session.model_dump(mode="json")

            state["answers"] = [
                answer.model_dump(mode="json")
                for answer in session.answers.values()
            ]

            # Existing Friend-4 evaluation pipeline.
            evaluation = evaluation_node(state)

            if evaluation.get("current_stage") == "error":
                raise HTTPException(
                    status_code=400,
                    detail=evaluation.get(
                        "errors",
                        ["Evaluation failed"],
                    ),
                )

            state.update(evaluation)
            sessions[session_id] = state

            return {
                "message": "Exam submitted and evaluated",
                "result": state.get("final_result"),
                "evaluation_results": state.get(
                    "evaluation_results",
                    [],
                ),
            }

        except HTTPException:
            raise
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=str(exc),
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Submission failed: {exc}",
            ) from exc


@app.get("/api/exams/{session_id}/results")
def get_results(
    session_id: str,
    user: dict[str, Any] = Depends(get_current_user),
):
    with sessions_lock:
        state = load_session(session_id)

        if state.get("_is_assignment"):
            raise HTTPException(
                status_code=409,
                detail="This is an examination assignment, not a student attempt",
            )

        if user["role"] == "student":
            if not _can_access_attempt(state, user):
                raise HTTPException(
                    status_code=403,
                    detail="You cannot access these results",
                )
        elif state.get("_owner_email") != user["email"]:
            raise HTTPException(
                status_code=403,
                detail="You cannot access these results",
            )

        result = state.get("final_result")

        if not result:
            raise HTTPException(
                status_code=409,
                detail="Results are available only after submission and evaluation",
            )

        return {
            "result": result,
            "evaluation_results": state.get(
                "evaluation_results",
                [],
            ),
        }

@app.get("/api/teacher/results")
def teacher_results(
    user: dict[str, Any] = Depends(require_role("teacher")),
):
    """
    Return every evaluated student attempt belonging to an exam created
    by the logged-in teacher.
    """
    rows: list[dict[str, Any]] = []

    with sessions_lock:
        for session_id, state in sessions.items():
            # Division assignment/template is not a student submission.
            if state.get("_is_assignment"):
                continue

            # Attempt was cloned from the teacher assignment, so ownership
            # remains attached to the private student attempt.
            if state.get("_owner_email") != user["email"]:
                continue

            final_result = state.get("final_result")
            evaluation_results = state.get("evaluation_results") or []

            # Not submitted/evaluated yet.
            if not final_result and not evaluation_results:
                continue

            detail_rows: list[dict[str, Any]] = []

            if isinstance(final_result, dict):
                maybe_rows = final_result.get("results")
                if isinstance(maybe_rows, list):
                    detail_rows = maybe_rows

            if not detail_rows and isinstance(evaluation_results, list):
                detail_rows = evaluation_results

            obtained = sum(
                float(item.get("marks_awarded", 0) or 0)
                for item in detail_rows
                if isinstance(item, dict)
            )
            total = sum(
                float(item.get("total_marks", 0) or 0)
                for item in detail_rows
                if isinstance(item, dict)
            )

            percentage = round((obtained / total) * 100, 2) if total else 0

            session_data = state.get("exam_session") or {}

            rows.append({
                "session_id": session_id,
                "assignment_id": state.get("_assignment_id"),
                "student_name": state.get("_student_name") or "Student",
                "student_usn": state.get("_student_usn") or "",
                "student_roll_number": state.get("_student_roll_number") or "",
                "division": state.get("_target_division") or "",
                "subject": state.get("_subject") or "",
                "topic": state.get("_topic") or "",
                "marks": obtained,
                "total_marks": total,
                "percentage": percentage,
                "status": (
                    final_result.get("status", "completed")
                    if isinstance(final_result, dict)
                    else session_data.get("status", "completed")
                ),
            })

    return {"results": rows}
