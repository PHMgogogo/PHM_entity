#!/usr/bin/env python3
"""Delete all OpenCode sessions (conversation history) on this machine.

Targets the SQLite database under the OpenCode data dir
(~/.local/share/opencode on this box = C:/Users/<you>/.local/share/opencode):

  - opencode.db  : the only db used by OpenCode v2

Deletion strategy (OpenCode v2 schema):
  PRAGMA foreign_keys = ON is enabled on the connection, then we delete every
  row from `session_v2`. The schema's ON DELETE CASCADE then automatically
  cleans the session-scoped children `session_message`, `session_inbox` and
  `session_pending`. Session-scoped rows in `event` / `event_sequence`
  (keyed by aggregate_id = session id, not FK-cascaded) are removed explicitly
  for the deleted session ids. The WAL is checkpointed afterwards so the change
  is fully persisted and OpenCode won't read stale data on next launch.

Safety:
  - DRY-RUN by default. Prints what WOULD be deleted, changes nothing.
    Pass --yes to actually delete.
  - Before deleting, the .db (+ -wal/-shm) files are copied into a
    timestamped backup folder, unless --no-backup is passed.

Run:
  python delete_opencode_sessions.py            # dry-run preview
  python delete_opencode_sessions.py --yes      # backup + delete all
  python delete_opencode_sessions.py --yes --no-backup   # delete, no backup

NOTE: close OpenCode first so its connection isn't writing the WAL while we run.
"""
import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DATA_DIR = Path.home() / ".local" / "share" / "opencode"
DBS = ["opencode.db"]
SESSION_TABLE = "session_v2"
CASCADE_CHILDREN = ["session_message", "session_inbox", "session_pending"]  # auto-cleaned via FK cascade
EVENT_TABLES = ["event", "event_sequence"]                                  # cleared per-session-id manually


def open_db(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys = ON;")  # MUST be on for ON DELETE CASCADE to fire
    return con


def count_rows(con: sqlite3.Connection, table: str):
    try:
        return con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    except sqlite3.OperationalError:
        return None  # table absent in this db


def compact(counts: dict) -> dict:
    return {k: v for k, v in counts.items() if v}


def purge_db(path: Path, commit: bool) -> None:
    print(f"\n=== {path.name} ===")
    if not path.exists():
        print("  (not found — skipped)")
        return

    con = open_db(path)
    tables = [SESSION_TABLE] + CASCADE_CHILDREN + EVENT_TABLES
    before = {t: count_rows(con, t) for t in tables}
    print("  before:", compact(before) or "all empty")

    # snapshot session ids BEFORE deleting (for event cleanup)
    try:
        ids = [r[0] for r in con.execute(f"SELECT id FROM {SESSION_TABLE}").fetchall()]
    except sqlite3.OperationalError:
        ids = []

    if commit and ids:
        placeholders = ",".join("?" * len(ids))
        con.execute(f"DELETE FROM {SESSION_TABLE};")  # cascades -> session_message/inbox/pending
        # events are keyed by aggregate_id = session id but not FK-cascaded; clear manually
        if count_rows(con, "event") and "event" in before:
            con.execute(f"DELETE FROM event WHERE aggregate_id IN ({placeholders})", ids)
        if count_rows(con, "event_sequence") and "event_sequence" in before:
            con.execute(f"DELETE FROM event_sequence WHERE aggregate_id IN ({placeholders})", ids)
        con.commit()
        con.execute("PRAGMA wal_checkpoint(TRUNCATE);")  # flush WAL into main file
    elif commit and not ids:
        print("  (no sessions — nothing to delete)")

    after = {t: count_rows(con, t) for t in tables}
    print("  after :", compact(after) or "all empty")
    con.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="Delete all OpenCode sessions.")
    ap.add_argument("--yes", action="store_true",
                    help="actually delete (default is a non-destructive dry-run)")
    ap.add_argument("--no-backup", action="store_true",
                    help="skip making a timestamped backup copy of the db files")
    ap.add_argument("--data-dir", default=str(DATA_DIR),
                    help=f"OpenCode data dir (default: {DATA_DIR})")
    args = ap.parse_args()

    base = Path(args.data_dir)
    print(f"OpenCode data dir: {base}")
    if not base.exists():
        sys.exit(f"ERROR: data dir not found: {base}")

    print("Mode:", "DELETE" if args.yes else "DRY-RUN (pass --yes to delete)")

    if args.yes and not args.no_backup:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        bak = base / f"backup-before-purge-{stamp}"
        bak.mkdir(exist_ok=True)
        for name in DBS + [f"{d}-wal" for d in DBS] + [f"{d}-shm" for d in DBS]:
            src = base / name
            if src.exists():
                shutil.copy2(src, bak / src.name)
        print(f"Backup written to: {bak}")

    for db in DBS:
        purge_db(base / db, commit=args.yes)

    print("\nDone.")


if __name__ == "__main__":
    main()
