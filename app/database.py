"""
app/database.py  –  Thin wrapper that points to your team's raha.db and helpers.

Your team's files:
  app/db_helpers.py  →  all query functions (create_user, get_user, save_scan, etc.)
  app/db_setup.py    →  create_tables()
  raha.db            →  the actual SQLite database file (in project root)
"""

from app.db_helpers import get_conn   # re-export so routes can use get_conn()
from app.db_setup import create_tables

# Path fix: make sure both files point to the same raha.db in the project root
import app.db_helpers as _h
import app.db_setup   as _s

_h.DB_PATH = 'raha.db'
_s.DB_PATH = 'raha.db'

__all__ = ['get_conn', 'create_tables']
