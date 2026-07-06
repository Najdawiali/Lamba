@echo off
set PYTHONIOENCODING=utf-8
set DATABASE_URL=postgresql+asyncpg://eagle:eagle_secret@localhost:5432/eagle_vision
set ELASTICSEARCH_URL=http://localhost:9200
cd /d C:\Users\alisa\Downloads\eagle_vision\backend
C:\Users\alisa\Downloads\eagle_vision\backend\venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000