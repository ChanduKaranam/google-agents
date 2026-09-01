#!/usr/bin/env bash
# Deploy the Clinical Case Simulator to Cloud Run as an A2A agent, ready to
# register with Gemini Enterprise.
#
#   ./deploy.sh
#   PROJECT=my-proj REGION=asia-south1 ./deploy.sh
#
# Two passes are required: Cloud Run assigns the service URL, and the agent
# card has to advertise that URL, so the service is redeployed with it set.
set -euo pipefail

# Prefer the project venv when one exists, so `python` and `adk` are the ones
# the case bank and tests were verified against.
if [[ -x "$(dirname "$0")/.venv/bin/python" ]]; then
  PATH="$(cd "$(dirname "$0")/.venv/bin" && pwd):${PATH}"
  export PATH
fi

PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-clinical-case-simulator}"
MODEL="${CS_MODEL:-gemini-2.5-flash}"
EVAL_MODEL="${CS_EVAL_MODEL:-gemini-2.5-pro}"

if [[ -z "${PROJECT}" ]]; then
  echo "No project set. Run: gcloud config set project YOUR_PROJECT" >&2
  exit 1
fi

echo "Project : ${PROJECT}"
echo "Region  : ${REGION}"
echo "Service : ${SERVICE}"
echo

echo "==> Validating the case bank"
python -m clinical_simulator.validate

echo
echo "==> Enabling required APIs"
gcloud services enable run.googleapis.com aiplatform.googleapis.com \
  cloudbuild.googleapis.com artifactregistry.googleapis.com --project "${PROJECT}"

deploy() {
  gcloud run deploy "${SERVICE}" \
    --source . \
    --project "${PROJECT}" \
    --region "${REGION}" \
    --no-allow-unauthenticated \
    --memory 1Gi \
    --cpu 1 \
    --timeout 900 \
    --set-env-vars "$1" \
    --quiet
}

BASE_ENV="GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_PROJECT=${PROJECT},GOOGLE_CLOUD_LOCATION=${REGION},CS_MODEL=${MODEL},CS_EVAL_MODEL=${EVAL_MODEL},CS_PRACTICE_MODE=TRUE"

echo
echo "==> Pass 1: deploying to obtain the service URL"
deploy "${BASE_ENV}"

URL="$(gcloud run services describe "${SERVICE}" --project "${PROJECT}" \
        --region "${REGION}" --format='value(status.url)')"

echo
echo "==> Pass 2: redeploying so the agent card advertises ${URL}"
deploy "${BASE_ENV},A2A_PUBLIC_URL=${URL}"

echo
echo "==> Granting Vertex AI access to the runtime service account"
SA="$(gcloud run services describe "${SERVICE}" --project "${PROJECT}" \
       --region "${REGION}" --format='value(spec.template.spec.serviceAccountName)')"
SA="${SA:-$(gcloud projects describe "${PROJECT}" --format='value(projectNumber)')-compute@developer.gserviceaccount.com}"
gcloud projects add-iam-policy-binding "${PROJECT}" \
  --member="serviceAccount:${SA}" --role="roles/aiplatform.user" \
  --condition=None --quiet >/dev/null
echo "    ${SA} -> roles/aiplatform.user"

echo
echo "==> Verifying the agent card"
TOKEN="$(gcloud auth print-identity-token)"
curl -sf -H "Authorization: Bearer ${TOKEN}" "${URL}/.well-known/agent-card.json" \
  | python -c "import json,sys; c=json.load(sys.stdin); print('    served card:', c.get('name'), '|', len(c.get('skills',[])), 'skills')" \
  || echo "    Could not read the agent card — check the service logs."

cat <<NEXT

Deployed: ${URL}

To register with Gemini Enterprise as an A2A agent:
  1. Gemini Enterprise console -> your app -> Agents -> Add agent -> A2A agent.
  2. Paste the agent card JSON printed by:
        python -m clinical_simulator.agent_card ${URL}
     If the console rejects that shape, retry with --v1.
  3. The service uses Cloud Run IAM for access control, so OAuth 2.0 client
     credentials are not required. Grant the Gemini Enterprise service agent
     roles/run.invoker on this service.

Alternative, and the simpler path if you do not need Cloud Run:
  ./deploy_agent_engine.sh   # deploys to Agent Runtime, register by resource path
NEXT
