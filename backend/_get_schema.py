"""Query PostgreSQL directly and write to UTF-8 file."""
import sys, os
sys.path.insert(0, os.getcwd())
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()

from upload.helpers import get_db
from sqlalchemy import text

out = []
def p(s=""): out.append(s)

engine = get_db()
with engine.connect() as conn:
    tables = conn.execute(text("""
        SELECT table_name, table_type FROM information_schema.tables
        WHERE table_schema = 'public' ORDER BY table_type, table_name
    """)).fetchall()
    p("=== TABLES & VIEWS ===")
    for t in tables:
        p(f"  {t[1]:20s} {t[0]}")

    cols = conn.execute(text("""
        SELECT table_name, column_name, data_type,
               character_maximum_length, is_nullable, column_default, ordinal_position
        FROM information_schema.columns WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position
    """)).fetchall()
    current_table = ''
    for c in cols:
        if c[0] != current_table:
            current_table = c[0]
            p(f"\n--- {current_table} ---")
        nullable = 'NULL' if c[4] == 'YES' else 'NOT NULL'
        maxlen = f"({c[3]})" if c[3] else ''
        default = f' DEFAULT {str(c[5])[:50]}' if c[5] else ''
        p(f"  {c[1]:35s} {c[2]}{maxlen:10s} {nullable:8s}{default}")

    p("\n=== PRIMARY KEYS ===")
    pks = conn.execute(text("""
        SELECT tc.table_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
        WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = 'public'
        ORDER BY tc.table_name, kcu.ordinal_position
    """)).fetchall()
    for pk in pks:
        p(f"  {pk[0]:30s} PK: {pk[1]}")

    p("\n=== FOREIGN KEYS ===")
    fks = conn.execute(text("""
        SELECT tc.table_name, kcu.column_name, ccu.table_name, ccu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
        ORDER BY tc.table_name
    """)).fetchall()
    for fk in fks:
        p(f"  {fk[0]}.{fk[1]}  -->  {fk[2]}.{fk[3]}")

    p("\n=== VIEW DEFINITIONS ===")
    views = conn.execute(text("""
        SELECT table_name, view_definition FROM information_schema.views
        WHERE table_schema = 'public' ORDER BY table_name
    """)).fetchall()
    for v in views:
        p(f"\n-- VIEW: {v[0]} --")
        p(v[1][:800] if v[1] else '(no definition)')

    p("\n=== ROW COUNTS ===")
    for t in tables:
        if t[1] == 'BASE TABLE':
            try:
                cnt = conn.execute(text(f"SELECT COUNT(*) FROM {t[0]}")).scalar()
                p(f"  {t[0]:30s} {cnt} rows")
            except Exception as e:
                p(f"  {t[0]:30s} (error: {e})")

with open("_schema_output.md", "w", encoding="utf-8") as f:
    f.write("\n".join(out))

print("DONE - wrote _schema_output.md")
