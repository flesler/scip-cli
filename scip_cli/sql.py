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
