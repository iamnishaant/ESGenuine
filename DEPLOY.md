# Deploying ESGenuine

The public deployment is two free services:

| Part | Host | Why this host |
|---|---|---|
| Dashboard (Vite static site) | Render static site, free | Serves the built React app; static sites never sleep |
| API (FastAPI) | Hugging Face Docker Space, free "CPU basic" (16 GB RAM) | The API holds ~1 GB (PyTorch + embedding model); Render's free 512 MB would crash it |

The dashboard reads claims straight from Supabase with the publishable key and calls the
API for integrity scores, fact-checks, benchmarks and the audit trail.

**The public deployment is read-only.** The API gets no `DATABASE_URL` (sign-up, login and
PDF ingest are disabled), no service-role key and no LLM key. The publishable key is in the
public JavaScript bundle by design: row-level security grants it `SELECT` only.

---

## 1. API on Hugging Face

1. Create a fine-grained GitHub token: *Repository access* → this repository only;
   *Permissions* → **Contents: Read-only**. The Space uses it only to clone during the build.
2. Create a Space: SDK **Docker**, hardware **CPU basic** (free), visibility **public**.
3. Space → *Settings* → *Variables and secrets*:

   | Name | Kind | Value |
   |---|---|---|
   | `GITHUB_TOKEN` | secret | the token from step 1 |
   | `JWT_SECRET` | secret | `python -c "import secrets; print(secrets.token_hex(32))"` |
   | `VITE_SUPABASE_URL` | variable | `https://<project-ref>.supabase.co` |
   | `VITE_SUPABASE_PUBLISHABLE_KEY` | variable | the publishable (anon) key |
   | `ENVIRONMENT` | variable | `production` |
   | `ALLOWED_ORIGIN_REGEX` | variable | `https://.*\.onrender\.com` |

4. Upload [`deploy/huggingface/Dockerfile`](deploy/huggingface/Dockerfile) and
   [`deploy/huggingface/README.md`](deploy/huggingface/README.md) to the Space. The build
   clones this repository, installs CPU-only PyTorch and bakes in the pinned embedding model.
   The first build takes 10–15 minutes.
5. Verify: `https://<hf-user>-<space-name>.hf.space/health` → `"ready": true`.

## 2. Dashboard on Render

Render → *New* → *Blueprint* → connect this repository. [`render.yaml`](render.yaml) defines
one static site; fill its three values when prompted:

- `VITE_API_BASE` — the Space URL from step 1.5
- `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY` — as above

Every push to `main` redeploys the dashboard automatically.

## Verify

Open the Render URL. The header should read **Connected**, and the Integrity Audit page
should show a score rather than "—". If it shows "Backend offline", check that
`VITE_API_BASE` is the Space URL and that the Space is awake (`/health`).

## Operating notes

- A free Space sleeps after ~48 hours without traffic; the first request wakes it in
  about a minute.
- A free Supabase project pauses after a week without activity; resume it from the
  Supabase dashboard.
- Custom domain: add it to the Space's `ALLOWED_ORIGINS` (comma-separated); no code change.
- Local development is unchanged: `start.bat`.

## API environment variables (reference)

| Variable | Public deployment | Purpose |
|---|---|---|
| `VITE_SUPABASE_URL` | required | Supabase REST reads (claims, reports, contradictions) |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | required | read-only key for the above |
| `ENVIRONMENT` | `production` | drops the localhost CORS origins; requires `JWT_SECRET` |
| `JWT_SECRET` | required in production | signs login tokens |
| `ALLOWED_ORIGIN_REGEX` / `ALLOWED_ORIGINS` | required | which dashboard origins may call the API |
| `DATABASE_URL` | **unset** | enables accounts (sign-up/login) and therefore ingest |
| `SUPABASE_SERVICE_ROLE_KEY` | **unset** | write path; bypasses RLS |
| `NVIDIA_API_KEYS` | **unset** | LLM for the `/audit/ask` Q&A |
| `PORT` | set by the host | the Space image listens on 7860 |
