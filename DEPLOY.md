# Deploying ESGenuine

The frontend reads live data two ways: **Supabase directly** (raw claims) and the
**FastAPI backend** (integrity scores, fact-check, benchmark, audit). Locally the
frontend falls back to `http://localhost:8000` for the backend, so a *hosted* UI needs
the backend hosted too. This guide deploys both.

`render.yaml` provisions both services as a Render Blueprint (free tier). Any Docker
host works for the backend (Railway / Fly.io / Cloud Run) — the Dockerfile already
binds `$PORT`; only the Render-specific wiring lives in `render.yaml`.

---

## One-time: get the values you'll paste as secrets

From the **Supabase dashboard** (Project → Settings):
- `VITE_SUPABASE_URL` — Data API → Project URL (`https://<ref>.supabase.co`)
- `VITE_SUPABASE_PUBLISHABLE_KEY` — Data API → anon/publishable key
- `DATABASE_URL` — Database → Connect → **Session pooler** (IPv4). It looks like
  `postgresql://postgres.<ref>:<password>@aws-1-<region>.pooler.supabase.com:5432/postgres`.
  **Do NOT use the direct `db.<ref>.supabase.co` string** — that host is IPv6-only and
  is unreachable from Render/Railway/Fly (this bit us repeatedly; see memory).

Optional:
- `NVIDIA_API_KEYS` — comma-separated NVIDIA NIM keys. Only the audit Q&A
  (`/audit/ask`) uses an LLM; the integrity score, fact-check and benchmark are
  deterministic and work without it.

---

## Deploy on Render (Blueprint)

1. Push this repo to GitHub (already on `origin`).
2. Render Dashboard → **New → Blueprint** → connect the repo → Render reads
   `render.yaml` and shows two services (`esgenuine-backend`, `esgenuine-frontend`).
3. Fill the `sync: false` secrets when prompted:
   - **backend**: `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY`,
     `DATABASE_URL` (pooler), `NVIDIA_API_KEYS` (optional). `JWT_SECRET` is
     auto-generated.
   - **frontend**: `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY`.
     `VITE_API_BASE` is wired to the backend automatically.
4. **Apply**. First build takes a while (the backend image pulls the torch/CUDA
   wheel stack). When the backend shows healthy (`/health` → `ready:true`) and the
   frontend is live, open the frontend URL.

CORS: the backend already accepts any `*.onrender.com` origin
(`ALLOWED_ORIGIN_REGEX` in `render.yaml`). For a **custom domain**, add it to the
backend's `ALLOWED_ORIGINS` env (comma-separated) — no code change.

---

## Verify

- `GET https://esgenuine-backend.onrender.com/health` → `{"ready": true, ...}`
- Frontend **Portfolio** / **Integrity Audit** pages show real scores (not "—" and no
  "Audit backend offline" banner). If you see the banner, the frontend can't reach the
  backend — check `VITE_API_BASE` and the backend's CORS/health.

## Backend env vars (reference)

| Var | Required | Purpose |
|-----|----------|---------|
| `VITE_SUPABASE_URL` | ✅ | Supabase REST reads (claims/reports/contradictions) |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | ✅ | anon key for the above |
| `DATABASE_URL` | auth only | `users` table via psycopg2 — **pooler (IPv4) URL** |
| `JWT_SECRET` | auth only | signs login tokens (Render auto-generates) |
| `NVIDIA_API_KEYS` | audit only | LLM for `/audit/ask`; scores are deterministic |
| `ALLOWED_ORIGINS` | — | extra exact CORS origins (custom domain) |
| `ALLOWED_ORIGIN_REGEX` | — | regex CORS origin (set to `*.onrender.com`) |
| `PORT` | — | injected by the host; Dockerfile defaults to 8000 |

## Free-tier caveat
Render's free web service sleeps after ~15 min idle (~50s cold start on the next
request). Fine for a demo; bump the plan for always-on.
