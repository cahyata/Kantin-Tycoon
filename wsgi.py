"""Titik masuk WSGI untuk hosting publik (mis. PythonAnywhere). Lihat docs/pasang-pythonanywhere.md."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server  # noqa: E402

server.ensure_db()
application = server.application
