"""
upload/helpers.py
─────────────────
Shared utilities for all upload routes:
  - DB connection from env
  - File reading (CSV + Excel)
  - Common normalisation functions
  - UploadResult dataclass
"""

import os
import re
import io
import logging
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

# ── DB engine (singleton) ─────────────────────────────────────────────────────

_engine: Engine | None = None

def get_db() -> Engine:
    global _engine
    if _engine is None:
        url = (
            os.getenv("DATABASE_URL")
            or (
                f"postgresql://"
                f"{os.getenv('DB_USER', 'postgres')}:"
                f"{os.getenv('DB_PASS', '')}@"
                f"{os.getenv('DB_HOST', 'localhost')}:"
                f"{os.getenv('DB_PORT', '5432')}/"
                f"{os.getenv('DB_NAME', 'college_monitoring')}"
            )
        )
        _engine = create_engine(url, echo=False, pool_pre_ping=True)
        log.info("DB engine created")
    return _engine


# ── UploadResult ──────────────────────────────────────────────────────────────

@dataclass
class UploadResult:
    upload_type: str
    total:    int = 0
    inserted: int = 0
    updated:  int = 0
    skipped:  int = 0
    errors:   list[str] = field(default_factory=list)

    def dict(self):
        return {
            "upload_type": self.upload_type,
            "total":    self.total,
            "inserted": self.inserted,
            "updated":  self.updated,
            "skipped":  self.skipped,
            "errors":   self.errors[:50],          # cap at 50 for API response
            "error_count": len(self.errors),
        }


# ── File reading ──────────────────────────────────────────────────────────────

def read_file(content: bytes, filename: str) -> pd.DataFrame | None:
    """Read CSV or Excel file bytes into a DataFrame. Returns None on failure."""
    try:
        if filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content), dtype=str, skipinitialspace=True)
        else:
            # Excel — always read first sheet
            df = pd.read_excel(io.BytesIO(content), sheet_name=0, dtype=str)
        df = df.dropna(how="all")
        log.info(f"Read {len(df)} rows from {filename}")
        return df
    except Exception as e:
        log.error(f"Could not read file: {e}")
        return None


def normalize_columns(df: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    """Lowercase + strip all columns, then rename using mapping."""
    df = df.copy()
    df.columns = df.columns.str.strip().str.lower()
    rename = {k.lower(): v for k, v in mapping.items() if k.lower() in df.columns}
    return df.rename(columns=rename)


# ── Field cleaners ────────────────────────────────────────────────────────────

def clean_str(val, max_len: int | None = None) -> str | None:
    if pd.isna(val): return None
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "-", "n/a", "null"): return None
    return s[:max_len] if max_len else s


def clean_phone(val) -> str | None:
    if pd.isna(val): return None
    s = str(val).strip().split(".")[0]        # remove .0 from Excel floats
    digits = re.sub(r"\D", "", s)
    return digits if 8 <= len(digits) <= 15 else None


def clean_reg(val) -> str | None:
    """Register number — strip float suffix, keep digits only."""
    if pd.isna(val): return None
    s = str(val).strip().split(".")[0]
    digits = re.sub(r"\D", "", s)
    return digits if len(digits) >= 6 else None


def clean_dob(val) -> datetime | None:
    if pd.isna(val): return None

    if isinstance(val, datetime):
        return val
    
    s = str(val).strip()
    s = s.split(" ")[0]

    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue

    return None

def clean_int(val) -> int | None:
    try:
        return int(float(str(val).strip()))
    except (ValueError, TypeError):
        return None


def clean_float(val) -> float | None:
    try:
        f = float(str(val).strip())
        return f if not pd.isna(f) else None
    except (ValueError, TypeError):
        return None


def normalize_hostel(val) -> str:
    
    s = str(val).strip().upper()
    s = re.sub(r"\s+", "", s)  # remove all spaces

    s = re.sub(r"[^A-Za-z]", "", s).upper()

    if any(x in s for x in ["HOSTEL", "HOSTELLER", "RESIDENT"]):
        return "Hosteller"

    if any(x in s for x in ["DAY", "DAYSCHOLAR"]):
        return "Day Scholar"

     # DEBUG (run once)
    print(f"RAW: {val} -> CLEAN: {s}")

    return "Day Scholar"


def normalize_status(val) -> str:
    if pd.isna(val): return "Active"
    s = re.sub(r"[\s_]", "", str(val)).upper()
    return {
        "ACTIVE":       "Active",
        "GRADUATED":    "Graduated",
        "PASSEDOUT":    "Graduated",
        "DROPOUT":      "Dropout",
        "DISCONTINUED": "Dropout",
        "DROPPED":      "Dropout",
    }.get(s, "Active")


def normalize_gender(val) -> str | None:
    if pd.isna(val): return None
    s = str(val).strip().upper()
    if s in ("M", "MALE"):   return "Male"
    if s in ("F", "FEMALE"): return "Female"
    if s:                    return "Other"
    return None


def normalize_grade(val) -> str | None:
    if pd.isna(val): return None
    g = str(val).strip().upper().replace(" ", "")
    return g if g in {"O", "A+", "A", "B+", "B", "C", "U", "AB"} else None


def normalize_month(val) -> str | None:
    if pd.isna(val): return None
    s = str(val).strip().upper()
    if any(x in s for x in ("MAY", "APR")): return "MAY"
    if any(x in s for x in ("NOV", "OCT")): return "NOV"
    return None


# ── DB lookup helpers ─────────────────────────────────────────────────────────

def get_dept_id(conn, code: str) -> int | None:
    row = conn.execute(
        text("SELECT department_id FROM departments WHERE department_code = :c"),
        {"c": code.strip().upper()}
    ).fetchone()
    return row[0] if row else None


def get_student_id(conn, reg: str) -> int | None:
    row = conn.execute(
        text("SELECT student_id FROM students WHERE register_number = :r"),
        {"r": reg}
    ).fetchone()
    return row[0] if row else None


def get_subject_id(conn, code: str) -> int | None:
    row = conn.execute(
        text("SELECT subject_id FROM subjects WHERE subject_code = :c"),
        {"c": code.strip().upper()}
    ).fetchone()
    return row[0] if row else None
