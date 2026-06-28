# AIBI4 V9 Deployment

V9 is independent from V8.

## Local run

```powershell
cd C:\Users\tarchi\AIBI4\v9\backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 9000
```

Open:

```text
http://localhost:9000
```

## Railway deployment as a separate service

Create a new Railway service for V9, not the existing V8 service.

Recommended settings, option A — repository root:

| Item | Value |
|---|---|
| Repository | `tad-s/AIBI4` |
| Root Directory | blank |
| Builder | Dockerfile |
| Dockerfile Path | `Dockerfile.v9` |
| Healthcheck Path | `/api/health` |

Recommended settings, option B — `v9` root:

| Item | Value |
|---|---|
| Repository | `tad-s/AIBI4` |
| Root Directory | `v9` |
| Builder | Dockerfile |
| Dockerfile Path | `Dockerfile` |
| Healthcheck Path | `/api/health` |

Required variables:

| Variable | Description |
|---|---|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Backend key. `service_role` is recommended for server-side Railway deployment if RLS blocks direct reads. |
| `OPENAI_API_KEY` | OpenAI API key |
| `OPENAI_MODEL` | Optional. Default is defined in code. |

## CLI deployment

If using Railway CLI, link to the V9 service and deploy from repository root.

```powershell
cd C:\Users\tarchi\AIBI4
railway link
railway up --dockerfile Dockerfile.v9
```

If the installed Railway CLI does not support `--dockerfile`, configure the service Build settings in the Railway UI:

- Builder: Dockerfile
- Dockerfile Path: `Dockerfile.v9`

Then run:

```powershell
railway up
```

## Notes

- V8 continues to use `Dockerfile` and `railway.json`.
- V9 uses `Dockerfile.v9` and should be deployed as a separate Railway service.
- Sessions are in-memory. Redeploying V9 resets active sessions.
