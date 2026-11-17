"""database.py: SAM's database, kept in an Excel workbook for now.

The team plan says "for now, an Excel sheet" with each student's user ID,
password and For you info. This is that sheet: data/sam_database.xlsx

    Users      One row per student: how they sign in, plus their survey answers
    Activity   Which websites students open and what subjects they ask SAM about.
               Used to rank the Popular near you page.
    Resources  Links students share on the Resources page
    Saved      Places each student saved to My plan, with the day they plan to go
    Languages  Made-up programming languages students create in the Code translator

Passwords are never saved. The "Password (hashed)" column holds a one-way
PBKDF2 hash, so nobody who opens the file can read a student's password.

You can open the file in Excel to look, but don't edit it while SAM is running:
SAM rewrites the whole file each time it saves. If you change it while SAM is
stopped, SAM reads your changes the next time it starts.

Swapping to a real database (SQLite, Postgres) later only means rewriting the
functions at the bottom of this file. The rest of SAM calls only those.
"""

import os
import re
import threading
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Font, PatternFill

DATA_DIR = Path(os.environ.get("SAM_DATA_DIR") or Path(__file__).resolve().parent / "data")
DB_PATH = DATA_DIR / "sam_database.xlsx"
MAX_TEXT = 2000  # Longest text SAM stores in one cell

# Each sheet's columns: (key used in code, header shown in Excel, column width)
SHEETS = {
    "Users": [
        ("user_id", "User ID", 10),
        ("username", "Username", 16),
        ("name", "First name", 14),
        ("email", "Email", 30),
        ("password_hash", "Password (hashed)", 22),
        ("provider", "Signs in with", 15),
        ("provider_id", "Google / Apple ID", 22),
        ("created", "Created", 17),
        ("last_sign_in", "Last sign-in", 17),
        ("age", "Age", 6),
        ("loc", "Where they live", 18),
        ("gender", "Gender", 12),
        ("plays_sports", "Interested in sports", 11),
        ("sports", "Sports", 30),
        ("sport_other", "Other sport", 16),
        ("vol", "Volunteering", 34),
        ("vol_other", "Other volunteering", 18),
        ("survey_saved", "Survey saved", 17),
        ("radius", "Travel distance (miles)", 12),
        ("lat", "Latitude", 11),
        ("lon", "Longitude", 11),
        ("place", "Place on the map", 22),
    ],
    "Activity": [
        ("time", "Time", 17),
        ("user_id", "User ID", 10),
        ("area", "Area", 14),
        ("category", "Category", 11),
        ("topic", "Topic", 22),
        ("title", "Title", 32),
        ("url", "Link", 44),
    ],
    "Resources": [
        ("posted", "Posted", 17),
        ("url", "Link", 44),
        ("posted_by", "Posted by", 16),
        ("age", "Age", 6),
        ("user_id", "User ID", 10),
    ],
    "Saved": [
        ("saved", "Saved", 17),
        ("user_id", "User ID", 10),
        ("kind", "Kind", 8),
        ("item_id", "Item ID", 20),
        ("title", "Title", 32),
        ("detail", "Detail", 24),
        ("address", "Address", 34),
        ("url", "Link", 44),
        ("lat", "Latitude", 11),
        ("lon", "Longitude", 11),
        ("date", "Planned day", 13),
        ("time", "Planned time", 12),
    ],
    "Languages": [
        ("saved", "Saved", 17),
        ("user_id", "User ID", 10),
        ("name", "Language", 18),
        ("spec", "Keywords (JSON)", 60),
    ],
}

# Hold `lock` while checking something and then writing, so two requests can't both pass the check.
lock = threading.RLock()
_cache = {"wb": None, "mtime": None}


# ---------- Reading and writing the workbook ----------

def _header(sheet, key):
    return next(h for k, h, _ in SHEETS[sheet] if k == key)


def _set_up(wb):
    """Make sure every sheet and column exists, with a bold, frozen header row."""
    for sheet, columns in SHEETS.items():
        if sheet not in wb.sheetnames:
            wb.create_sheet(sheet)
        ws = wb[sheet]
        have = {c.value for c in ws[1] if c.value}
        next_col = len([c for c in ws[1] if c.value]) + 1
        for _, header, width in columns:
            if header in have:
                continue
            cell = ws.cell(row=1, column=next_col, value=header)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="0F766E")
            ws.column_dimensions[cell.column_letter].width = width
            next_col += 1
        ws.freeze_panes = "A2"
    # A new workbook starts with an empty "Sheet"; drop it.
    if "Sheet" in wb.sheetnames and "Sheet" not in SHEETS and wb["Sheet"].max_row == 1 and wb["Sheet"]["A1"].value is None:
        del wb["Sheet"]


def _open():
    """The workbook, read again if the file changed since SAM last read it."""
    mtime = DB_PATH.stat().st_mtime_ns if DB_PATH.exists() else None
    if _cache["wb"] is None or mtime != _cache["mtime"]:
        wb = load_workbook(DB_PATH) if mtime is not None else Workbook()
        _set_up(wb)
        _cache.update(wb=wb, mtime=mtime)
    return _cache["wb"]


def _save(wb):
    """Write to a temporary file first, so a crash mid-save can't corrupt the database."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = DB_PATH.with_name(DB_PATH.stem + ".saving.xlsx")
    wb.save(tmp)
    os.replace(tmp, DB_PATH)
    _cache["mtime"] = DB_PATH.stat().st_mtime_ns


def _columns(ws):
    return {c.value: c.column for c in ws[1] if c.value}


def _put(cell, value):
    if isinstance(value, str):
        value = ILLEGAL_CHARACTERS_RE.sub("", value).strip()[:MAX_TEXT]
        cell.value = value or None
        if value:
            # Always text, never a formula, even if a student types "=SUM(...)".
            cell.data_type = "s"
    else:
        cell.value = value
        if isinstance(value, datetime):
            cell.number_format = "yyyy-mm-dd hh:mm"


def _row_dict(sheet, values, cols):
    row = {}
    for key, header, _ in SHEETS[sheet]:
        i = cols.get(header)
        value = values[i - 1] if i and i - 1 < len(values) else None
        row[key] = "" if value is None else value
    return row


def now():
    return datetime.now().replace(microsecond=0)


# ---------- What the rest of SAM calls ----------

def rows(sheet):
    """Every row of a sheet, as dicts keyed by the names in SHEETS."""
    with lock:
        ws = _open()[sheet]
        cols = _columns(ws)
        return [
            _row_dict(sheet, values, cols)
            for values in ws.iter_rows(min_row=2, values_only=True)
            if any(v not in (None, "") for v in values)
        ]


def add_row(sheet, fields):
    with lock:
        wb = _open()
        ws = wb[sheet]
        cols = _columns(ws)
        r = ws.max_row + 1
        for key, value in fields.items():
            _put(ws.cell(row=r, column=cols[_header(sheet, key)]), value)
        _save(wb)


def _matching_rows(ws, cols, sheet, where):
    """Row numbers whose columns equal every value in `where`, for example {"user_id": "U0001"}."""
    wanted = [(cols[_header(sheet, key)], str(value)) for key, value in where.items()]
    return [r for r in range(2, ws.max_row + 1)
            if all(str(ws.cell(row=r, column=col).value or "") == value for col, value in wanted)]


def update_rows(sheet, where, fields):
    """Change every row that matches `where`. Returns how many rows changed."""
    with lock:
        wb = _open()
        ws = wb[sheet]
        cols = _columns(ws)
        found = _matching_rows(ws, cols, sheet, where)
        for r in found:
            for key, value in fields.items():
                _put(ws.cell(row=r, column=cols[_header(sheet, key)]), value)
        if found:
            _save(wb)
        return len(found)


def update_row(sheet, key, match, fields):
    """Change the rows whose `key` column equals `match`. Returns False if none does."""
    return update_rows(sheet, {key: match}, fields) > 0


def delete_rows(sheet, where):
    """Remove every row that matches `where`. Returns how many rows were removed."""
    with lock:
        wb = _open()
        ws = wb[sheet]
        found = _matching_rows(ws, _columns(ws), sheet, where)
        for r in reversed(found):  # Bottom up, so the row numbers above stay right
            ws.delete_rows(r)
        if found:
            _save(wb)
        return len(found)


def add_user(fields):
    """Add a student and return their new user ID (U0001, U0002, ...)."""
    with lock:
        numbers = [int(m.group(1)) for u in rows("Users") if (m := re.fullmatch(r"U(\d+)", str(u["user_id"])))]
        user_id = f"U{max(numbers, default=0) + 1:04d}"
        add_row("Users", {**fields, "user_id": user_id, "created": now()})
        return user_id
