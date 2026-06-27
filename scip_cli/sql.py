"""SQLite helpers shared across query modules."""

import logging

logger = logging.getLogger(__name__)


def debug_execute(db, sql, params=()):
    """Execute SQL with optional debug logging."""
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("SQL: %s | params: %s", sql.strip()[:200], params)
    return db.execute(sql, params)


def escape_like(s):
    """Escape SQL LIKE special characters in a string."""
    return s.replace("%", "\\%").replace("_", "\\_")


def configure_read_connection(db):
    """Tune SQLite for read-heavy CLI queries."""
    db.executescript("""
        PRAGMA query_only = ON;
        PRAGMA temp_store = MEMORY;
        PRAGMA cache_size = -64000;
        PRAGMA mmap_size = 268435456;
    """)
