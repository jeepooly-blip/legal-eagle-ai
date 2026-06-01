# Deployment Guide: GitHub + Vercel + Railway

Step-by-step instructions to put Legal Eagle AI on the public internet.

## Architecture

```
                ┌──────────────────────────────┐
                │  Vercel (static frontend)    │
                │  index.html, app.js, style   │
                │  https://legal-eagle-ai      │
                │          .vercel.app         │
                └──────────────┬───────────────┘
                               │ fetch API
                               ▼
                ┌──────────────────────────────┐
                │  Railway (FastAPI backend)   │
                │  uvicorn legal_eagle.api     │
                │  https://legal-eagle-api     │
                │     .up.railway.app          │
                └──────────────┬───────────────┘
                               │
                ┌──────────────┼───────────────┐
                ▼              ▼               ▼
          CourtListener     EUR-Lex       EuroVoc
            (US)          (EU SPARQL)    (EU SPARQL)
```

- **Vercel** serves the static `index.html` (and `app.js` + `style.css`) — free, instant global CDN, custom domain support.
- **Railway** runs the Python FastAPI backend 24/7 with no timeout (Vercel serverless has a 10s limit on the free tier; our pipeline takes 20-40s).
- **Both auto-deploy from the same GitHub repo** on every push to `main`.

---

## Step 1 — Create a GitHub account (skip if you have one)

Go to https://github.com/signup and create a free account. Verify your email.

---

## Step 2 — Create the GitHub repository

1. Go to https://github.com/new
2. **Repository name:** `legal-eagle-ai` (or whatever you want)
3. **Description:** `Multi-agent cross-jurisdictional legal research platform`
4. **Public** (so Vercel/Railway can read it for free)
5. **Do NOT** check "Add a README" / ".gitignore" / "license" — we have our own.
6. Click **Create repository**

GitHub will show you a page with the repo URL, e.g. `https://github.com/YOUR_USERNAME/legal-eagle-ai`.

---

## Step 3 — Push your local code to GitHub

Open PowerShell in your project folder and run:

```powershell
cd C:\Users\hamad\le_build

# Initialize git (only once, if you haven't)
git init
git config user.name "Your Name"
git config user.email "you@example.com"

# Add ALL files (the .gitignore excludes junk automatically)
git add .

# Verify what will be committed (should NOT include .venv, .env, server.log, etc.)
git status

# First commit
git commit -m "Initial commit: v0.1.0 MVP with EuroVoc integration"

# Add the remote and push
git remote add origin https://github.com/YOUR_USERNAME/legal-eagle-ai.git
git branch -M main
git push -u origin main
```

When prompted, sign in to GitHub. If you have 2FA enabled, use a **Personal Access Token** (PAT) instead of your password:

- Go to https://github.com/settings/tokens/new
- Scopes: `repo` (full control of private repositories)
- Copy the token, paste it as the password when `git push` prompts.

After the push, refresh the GitHub repo page — you should see all the files.

---

## Step 4 — Deploy the backend to Railway

1. Go to https://railway.app and sign up with your GitHub account (one click).
2. Click **New Project** → **Deploy from GitHub repo** → select `legal-eagle-ai`.
3. Railway will auto-detect Python via Nixpacks. Wait for the first build to finish (~3-5 min).
4. Click on the deployed service → **Variables** tab → add these env vars:

   | Name | Value |
   |---|---|
   | `MINIMAX_API_KEY` | your actual key (e.g. `sk-...`) |
   | `MINIMAX_MODEL` | `minimax/minimax-M3` (or whatever the LLM provider uses) |
   | `COURTLISTENER_BASE_URL` | `https://www.courtlistener.com` |
   | `EURLEX_BASE_URL` | `https://eur-lex.europa.eu` |
   | `EUROVOC_SPARQL_URL` | `https://publications.europa.eu/webapi/rdf/sparql` |
   | `SUPABASE_URL` | (optional) your Supabase project URL |
   | `SUPABASE_KEY` | (optional) your Supabase anon key |
   | `LOG_LEVEL` | `INFO` |

5. Click **Settings** → **Networking** → **Generate Domain**. You'll get a URL like `legal-eagle-api.up.railway.app`. **Copy this URL** — you need it for the frontend.

6. Test the backend in your browser: open `https://legal-eagle-api.up.railway.app/healthz` — you should see `{"status":"ok"}`.

7. Test a real research from PowerShell:
   ```powershell
   curl -X POST https://legal-eagle-api.up.railway.app/research `
     -H "Content-Type: application/json" `
     -d '{"query":"Compare US Fourth Amendment with EU GDPR"}'
   ```
   You should get `{"session_id":"..."}` back within ~30s.

---

## Step 5 — Connect the frontend to the backend

Open `app.js` in your project and replace the placeholder URL at the top:

```js
const API_BASE = "https://legal-eagle-api.up.railway.app";  // <-- paste your Railway URL
```

Commit and push:

```powershell
git add app.js
git commit -m "Point frontend at Railway backend"
git push
```

---

## Step 6 — Deploy the frontend to Vercel

1. Go to https://vercel.com and sign up with your GitHub account.
2. Click **Add New…** → **Project** → import the `legal-eagle-ai` repo.
3. Vercel will auto-detect it as a static site. Settings:
   - **Framework Preset:** Other
   - **Root Directory:** `./` (leave as is)
   - **Build Command:** leave empty
   - **Output Directory:** leave empty (Vercel will auto-serve the root)
4. Click **Deploy**. Wait ~30s.
5. Vercel gives you a URL like `https://legal-eagle-ai.vercel.app`. Open it.

You should see the Legal Eagle dashboard. The status pill in the top right should turn **green** showing the Railway backend URL.

---

## Step 7 — Add a custom domain (optional)

**Vercel:** Project → **Settings** → **Domains** → type your domain (e.g. `legal-eagle.ai`) → follow the DNS instructions.

**Railway:** Service → **Settings** → **Networking** → **Custom Domain** → follow DNS instructions.

---

## Troubleshooting

### "Failed to fetch" in the browser
- The Railway backend hasn't finished deploying yet — wait 2-3 min.
- The `API_BASE` in `app.js` is wrong — re-check.
- CORS is allowed (we set `allow_origins=["*"]` in `api/main.py`), so this should not be the issue.

### "uvicorn: command not found" on Railway
- Check the build logs. Railway's Nixpacks should auto-install from `pyproject.toml`. If not, add a `requirements.txt`:
  ```bash
  pip freeze > requirements.txt
  git add requirements.txt
  git commit -m "Add requirements.txt for Railway"
  git push
  ```

### Railway says "Application failed to respond"
- Check the deploy logs. The most common cause is a missing `MINIMAX_API_KEY`. Set it in the Variables tab.
- Visit `/healthz` to confirm the app started.

### Tests fail on GitHub Actions
- Check `.github/workflows/ci.yml`. The `MINIMAX_API_KEY` and other env vars are set to dummy values for the test step; if your tests need real network, you may need to update the conftest.

### Vercel says "No build output"
- This repo is a static site, not a framework project. If Vercel expects a build, ensure `vercel.json` is at the root and there are no `package.json` files. The current config is correct.

### Vercel free tier 10s timeout
- This is **why** the backend is on Railway, not Vercel. The Vercel-hosted frontend just makes HTTP calls — no serverless function involved.

---

## Updating after initial deploy

After the initial setup, the workflow is:

1. Edit code locally.
2. `git add .`
3. `git commit -m "describe what changed"`
4. `git push`
5. Both Vercel and Railway auto-deploy within ~30-90s.

---

## Cost summary

| Service | Free tier | What you get |
|---|---|---|
| **GitHub** | Unlimited public repos | Source control + Actions (2000 CI min/month) |
| **Vercel** | 100 GB bandwidth/mo, unlimited sites | Static hosting with global CDN + custom domain |
| **Railway** | $5 credit/month (~500 hrs) | 24/7 Python app with 8 GB RAM, 8 GB disk |
| **Supabase** | 500 MB database, 2 GB bandwidth | Postgres + auth + storage |

Total: **$0/month** for a working production deployment at low traffic. If you exceed Railway's free credit, the next tier is $5/mo + usage.

---

## Syncing back to OneDrive (optional)

If you want a local backup in your OneDrive folder, after each deploy:

```powershell
robocopy "C:\Users\hamad\le_build" "C:\Users\hamd\OneDrive\Desktop\legal eagle PRd" /MIR /XD .venv .pytest_cache .ruff_cache __pycache__ .git /XF *.log
```

(`/MIR` mirrors the directory; the `/XD` and `/XF` exclusions match `.gitignore`.)

---

That's it! You now have a public legal research app backed by a multi-agent Python pipeline, with continuous deployment on every git push.
