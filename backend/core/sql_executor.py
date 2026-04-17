import logging
import time
from sqlalchemy import text
from upload.helpers import get_db

log = logging.getLogger(__name__)
MAX_ROWS = 100

class Result:
    def __init__(self, rows, row_count, columns=None, error=None,
                 execution_ms=0.0, truncated=False, warning=None):
        self.rows         = rows
        self.row_count    = row_count
        self.columns      = columns or (list(rows[0].keys()) if rows else [])
        self.error        = error
        self.execution_ms = execution_ms
        self.truncated    = truncated
        self.warning      = warning

class SQLExecutor:
    async def init_pool(self):
        pass

    async def close(self):
        pass

    async def run(self, sql: str, params: dict = None, role: str = "hod"):
        engine = get_db()
        start  = time.perf_counter()
        try:
            with engine.connect() as conn:
                if params:
                    result = conn.execute(text(sql), parameters=params)
                else:
                    result = conn.execute(text(sql))
                rows    = [dict(r._mapping) for r in result]
                elapsed = (time.perf_counter() - start) * 1000
                truncated = len(rows) > MAX_ROWS
                if truncated:
                    rows = rows[:MAX_ROWS]
                return Result(
                    rows=rows,
                    row_count=len(rows),
                    execution_ms=round(elapsed, 1),
                    truncated=truncated,
                    warning=f"Results truncated to {MAX_ROWS} rows." if truncated else None,
                )
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            log.error(f"SQL execution error: {e}")
            return Result(rows=[], row_count=0, error=str(e), execution_ms=round(elapsed, 1))

executor = SQLExecutor()

def get_executor():
    return executor

def generate_summary(question: str, rows: list, row_count: int) -> str:
    """Generate a human-friendly summary from query results."""
    q = question.lower()
    if row_count == 0:
        return "No results found for your question."
    if row_count == 1 and rows:
        # Single row — likely a count or aggregate
        first = rows[0]
        vals  = list(first.values())
        keys  = list(first.keys())
        if len(vals) == 1:
            return f"The answer is **{vals[0]}**."
        pairs = ", ".join(f"{k}: {v}" for k, v in first.items())
        return f"Found 1 result — {pairs}."
    # Multiple rows
    if any(kw in q for kw in ["how many", "count", "total"]):
        v = list(rows[0].values())[0] if rows else 0
        return f"**{v}** records match your query."
    return f"Found **{row_count}** result{'s' if row_count != 1 else ''}."
