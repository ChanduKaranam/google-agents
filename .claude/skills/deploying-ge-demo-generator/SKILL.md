---
name: deploying-ge-demo-generator
description: "Use when deploying, redeploying, or troubleshooting Google's GE Demo Generator Apps Script app (GoogleCloudPlatform/generative-ai → search/gemini-enterprise/ge-demo-generator), or when hitting clasp push/login failures, Apps Script OAuth errors (restricted_client, access_denied), GCP project link errors, or Usage_Logs sheet problems while standing it up."
---

# Deploying the GE Demo Generator

Apps Script web app that generates Gemini Enterprise demo environments. Deploying it is ~10 minutes of work wrapped in ~6 undocumented failure modes. This skill is the runbook that skips them.

**Core principle: verify the environment BEFORE choosing the access model.** The app's README assumes a Google Workspace domain. If you pick `DOMAIN` access and Workspace turns out to be absent, you rework the manifest, the version, and the deployment.

## Phase 0 — Preflight (do this first, always)

Run all four. Each one decides a later choice.

```bash
export CLOUDSDK_CONFIG="$WINDOWS_GCLOUD_CONFIG"   # WSL only; see gcloud-wsl-windows-config
gcloud organizations list                          # 0 items → NO Workspace org
gcloud projects describe $PROJECT --format='yaml(projectNumber,parent)'
gcloud projects get-iam-policy $PROJECT --flatten='bindings[].members' \
  --filter="bindings.members:$USER_EMAIL" --format='value(bindings.role)'
node -v
```

| Preflight result | What it forces |
|---|---|
| No org / no `parent` | `access: ANYONE`, consent screen **External + Testing**. `DOMAIN` and Internal are impossible. |
| No `roles/editor`/`owner` | Linking the GCP project will fail. Need `resourcemanager.projects.update`. |
| Node ≠ 22 | clasp will fail. `nvm use 22` for every clasp command. |
| `projectNumber` | Required (not project ID) for the GCP link step. |

A custom-domain email (`you@yourcompany.com`) does **not** mean Workspace. Only `gcloud organizations list` answers that.

## Phase 1 — Local setup

```bash
git clone --depth 1 --filter=blob:none --sparse \
  https://github.com/GoogleCloudPlatform/generative-ai.git
cd generative-ai && git sparse-checkout set search/gemini-enterprise/ge-demo-generator
cd search/gemini-enterprise/ge-demo-generator

gcloud services enable aiplatform.googleapis.com bigquery.googleapis.com \
  drive.googleapis.com sheets.googleapis.com script.googleapis.com --project $PROJECT
```

**Enable the Apps Script API for the *account*** (a per-user toggle, not a project setting): https://script.google.com/home/usersettings

## Phase 2 — clasp

Prefix **every** clasp command with `nvm use 22`.

```bash
export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh"; nvm use 22
```

Login — run it **backgrounded with the loopback flow**, not `--no-localhost`. Harness `!` shells can't supply interactive stdin, so the paste prompt dies. Loopback needs no stdin: clasp prints a URL, you open it in the browser, WSL2 forwards the callback, clasp exits on its own.

```bash
npx --yes @google/clasp@latest login &      # then read the URL from its output
npx --yes @google/clasp@latest create-script --title "GE Demo Generator" \
  --type standalone --rootDir app           # NOT --type webapp (rejected)
```

**`create-script` overwrites `app/appsscript.json` with a default stub** — wiping oauthScopes, BigQuery/Sheets advanced services, and the webapp block. Restore the file before pushing, every time. Verify with `grep oauthScopes app/appsscript.json`.

Set `webapp.access` per Phase 0, then:

```bash
npx --yes @google/clasp@latest push --force
npx --yes @google/clasp@latest create-version "$(grep APP_VERSION: app/Code.gs | head -1 | sed "s/.*'\(.*\)'.*/\1/")"
npx --yes @google/clasp@latest create-deployment -d "..."
```

## Phase 3 — Console wiring (UI only, in this order)

Order matters: each step's failure is caused by skipping the previous one.

1. **Link GCP project** — Editor ⚙️ Project Settings → GCP Project → Change project → **project number**. Fails with *"Project does not exist or you need edit access"* when you lack `resourcemanager.projects.update` — that message means permissions, not a wrong number. With `projectIamAdmin` you can self-grant `roles/editor` and revoke it after linking.
2. **OAuth consent screen** — `https://console.cloud.google.com/auth/overview?project=$PROJECT`. External, publishing status **Testing** (never Publish — that triggers weeks of verification for the Drive/Sheets scopes). Add yourself under **Test users**.
3. **Script Properties** — `PROJECT_ID`, `LOG_SHEET_URL`. Both mandatory; `doGet` serves `SetupError.html` without them. Set these before authorizing.
4. **Authorize** — run **`forceAuthorize`**. The README's `forceAuthorizeSpreadsheet` does not exist.

## Phase 4 — The log sheet

The **tab** must be named `Usage_Logs`. Naming the *file* that is the most common mistake and the failure surfaces only at the end of a generation run, after the expensive Gemini work.

Do not add headers — `ensureLogSheetHeaders()` overwrites row 1 automatically.

## Error → cause

| Symptom | Cause |
|---|---|
| `Premature close` on oauth2.googleapis.com | Node 24. Use Node 22. Not network, not scopes. |
| `Insufficient Permission` from clasp | Real scope problem (e.g. `--adc`, which lacks `script.projects`). Needs `clasp login`. |
| `Error 403: restricted_client` | No OAuth consent screen on the project. |
| `Error 403: access_denied` | Consent screen exists; you're not in Test users. |
| "Project does not exist or you need edit access" | Missing `resourcemanager.projects.update`. |
| `Invalid container file type` | `create-script --type webapp`. Use `standalone`. |
| Web app shows red setup-error page | `PROJECT_ID` / `LOG_SHEET_URL` unset. |
| Push succeeds, scopes vanish | `create-script` clobbered the manifest. |

## Verification — what actually proves it works

`forceAuthorize` logging `✅ Spreadsheet Access: OK (Name)` prints `ss.getName()`, the **file** title. It does not prove the tab exists. Neither does `checkSpreadsheet` in the execution log — it *returns* JSON rather than logging it, so the log shows only "Execution completed".

Check the tab visually, then generate one throwaway demo end to end. A header row plus one data row in the sheet is the only real proof.

## Access model consequences

With `executeAs: USER_DEPLOYING` + `access: ANYONE` (the no-Workspace outcome):

- Only the deployer authorizes; colleagues need no IAM and no consent.
- Anyone with the URL spends the deployer's Vertex quota. Treat the link as a secret.
- `Session.getActiveUser().getEmail()` returns empty for visitors — usage attribution, history, and favorites degrade.
- Kill switch: `clasp delete-deployment <id>`.

Each colleague still needs their own GCP project with billing, ~15 APIs, and IAM rights to run the generated setup script; remind them of `--cleanup`.

## Updating later

Bump `APP_VERSION` in `app/Code.gs`, then under `nvm use 22`:
`DEPLOYMENT_ID=<id> bash deploy.sh` (`clasp version` still resolves as an alias of `create-version`).
