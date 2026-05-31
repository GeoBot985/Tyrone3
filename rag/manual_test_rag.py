from rag.db import get_connection, init_db
from rag.ingest import ingest_pdf
from rag.search import search

conn = get_connection()
init_db(conn)

ingest_pdf("sample.pdf", conn)

results = search(conn, "What is this document about?")
for r in results:
    print(r)
