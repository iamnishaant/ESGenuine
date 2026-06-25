# ESGenuine

ESG report claim-verification platform. It parses ESG PDFs, extracts and scores
claims (groundability), and detects contradictions across reports. A React
dashboard visualizes the results from Supabase.

## Structure

```
.
├── frontend/     # Vite + React + TypeScript dashboard (shadcn/ui, Tailwind)
├── backend/      # FastAPI: PDF parsing, claim extraction, NLI contradiction reasoning
├── supabase/     # Supabase edge functions (claim analysis)
├── docs/         # Planning docs (Execution Plan, Weekly Plan, command notes)
├── .venv/        # Python virtual environment for the backend
└── .env          # Shared env: VITE_* (frontend) + GROQ_API_KEY / DATABASE_URL (backend)
```

## Frontend

```sh
cd frontend
npm install          # first time only
npm run dev          # http://localhost:8080
npm run build        # production build -> frontend/dist
```

The frontend reads the shared `.env` at the repo root via Vite's `envDir`. Only
`VITE_`-prefixed vars are exposed to the client. It calls the backend at
`http://localhost:8000` and reads claim data directly from Supabase.

## Backend

```sh
# from the repo root
.\.venv\Scripts\activate                 # Windows (use source .venv/bin/activate on *nix)
pip install -r backend/requirements.txt  # first time only
cd backend
uvicorn src.api.server:app --reload      # http://localhost:8000
```

## Environment

Copy `.env.example` to `.env` and fill in:

- `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY`, `VITE_SUPABASE_PROJECT_ID` — frontend
- `GROQ_API_KEY` — backend claim extraction (Groq llama-3.1-8b)
- `DATABASE_URL` — backend DB setup/maintenance scripts
