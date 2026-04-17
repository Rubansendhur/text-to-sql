# DCS Monitor

A full-stack college monitoring app with a FastAPI backend, React frontend, PostgreSQL data access, and a Qdrant-powered few-shot retrieval layer for natural-language to SQL queries.

## What it does

- Query students, faculty, subjects, timetables, and arrears in natural language
- Use RAG to retrieve relevant few-shot Q→SQL examples from Qdrant
- Support chat feedback with thumbs up/down
- Upload and manage academic data through the UI

## Project Structure

- `backend/` - FastAPI app, SQL generation, intent handling, Qdrant integration, upload routes
- `frontend/` - Vite + React UI
- `Test-files/` - sample CSV/XLSX files for testing uploads

## Requirements

- Python 3.10+ recommended
- Node.js 18+ recommended
- PostgreSQL database
- Ollama running locally for embeddings and SQL generation helpers
- Qdrant either in local embedded mode or as a Docker service

## Backend Setup

1. Create and activate a Python virtual environment.
2. Install dependencies:

   ```bash
   cd backend
   python -m pip install -r requirements.txt
   ```

3. Configure environment variables in `backend/.env`.

   Required database settings:

   - `DB_USER`
   - `DB_PASS`
   - `DB_HOST`
   - `DB_PORT`
   - `DB_NAME`

   Qdrant options:

   - Local embedded mode: `QDRANT_PATH=.qdrant_data`
   - Docker/server mode: uncomment `QDRANT_URL=http://localhost:6333`

4. Start the backend:

   ```bash
   cd backend
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

## Qdrant

### Option 1: Embedded local storage

This is the default in the current `.env`.

- Data is stored under `backend/.qdrant_data`
- No Docker container is needed
- Seed the collection with:

  ```bash
  cd backend
  python scripts/seed_qdrant.py
  ```

### Option 2: Docker service

If you prefer a Qdrant server with a dashboard:

```powershell
docker run --name qdrant-local -p 6333:6333 -p 6334:6334 -v "D:/C/cit-22smcb0055/SEM-VIII/GEN-AI/Collge-monitoring/new_code/qdrant_storage:/qdrant/storage" qdrant/qdrant
```

Then set:

```env
QDRANT_URL=http://localhost:6333
# QDRANT_PATH=.qdrant_data
```

Dashboard:

- http://localhost:6333/dashboard

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server will start on the default local port.

## Common Notes

- The backend uses Ollama embeddings through `nomic-embed-text`.
- The RAG engine seeds curated few-shot examples from `backend/data/few_shot.py` into Qdrant.
- Chat intent handling is split into greeting, chitchat, clarification, and data query paths to reduce incorrect SQL generation.

## Useful Files

- `backend/main.py` - FastAPI entry point
- `backend/core/rag_engine.py` - RAG and SQL generation flow
- `backend/core/qdrant_store.py` - Qdrant client and collection helpers
- `backend/scripts/seed_qdrant.py` - seed examples into Qdrant
- `frontend/src/pages/Chat.jsx` - chat UI

## License

No license file is currently included.
