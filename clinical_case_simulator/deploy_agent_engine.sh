#!/usr/bin/env bash
# Deploy to Vertex AI Agent Engine (Agent Runtime).
#
# The simplest route to Gemini Enterprise: no agent card, no A2A plumbing, no
# two-pass URL dance. Registration takes the resource path
# projects/PROJECT/locations/LOCATION/reasoningEngines/RESOURCE_ID.
#
# Use deploy.sh instead if you need Cloud Run — for IAM control, VPC access,
# or to run the same container elsewhere.
set -euo pipefail

# Prefer the project venv when one exists, so `python` and `adk` are the ones
# the case bank and tests were verified against.
if [[ -x "$(dirname "$0")/.venv/bin/python" ]]; then
  PATH="$(cd "$(dirname "$0")/.venv/bin" && pwd):${PATH}"
  export PATH
fi

PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-us-central1}"

if [[ -z "${PROJECT}" ]]; then
  echo "No project set. Run: gcloud config set project YOUR_PROJECT" >&2
  exit 1
fi

echo "==> Validating the case bank"
python -m clinical_simulator.validate

echo
echo "==> Enabling required APIs"
gcloud services enable aiplatform.googleapis.com --project "${PROJECT}"

echo
echo "==> Deploying to Agent Engine"
# Add --agent_engine_id RESOURCE_ID to update an existing deployment in place
# instead of creating a new one.
# Sessions are in-memory by default and are lost on restart. For persistent
# student history, add:
#   --session_service_uri "agentengine://RESOURCE_ID"
LOG="$(mktemp)"
adk deploy agent_engine \
  --project "${PROJECT}" \
  --region "${REGION}" \
  --display_name "Clinical Case Simulator" \
  --description "AI virtual patient for MBBS students: history taking, clinical reasoning and scored feedback." \
  ${AGENT_ENGINE_ID:+--agent_engine_id "${AGENT_ENGINE_ID}"} \
  clinical_simulator 2>&1 | tee "${LOG}"

# `adk deploy` exits 0 even when the deployment fails, so check the output.
if grep -qi "deploy failed" "${LOG}"; then
  echo
  echo "Deployment FAILED — see the error above." >&2
  exit 1
fi

RESOURCE="$(grep -oE 'projects/[^ ]*/locations/[^ ]*/reasoningEngines/[0-9]+' "${LOG}" | tail -1 || true)"

cat <<NEXT

Next: register in Gemini Enterprise.
  Console -> your app -> Agents -> Add agent -> "Custom agent via Agent Runtime"
  Resource path: ${RESOURCE:-projects/${PROJECT}/locations/${REGION}/reasoningEngines/RESOURCE_ID}

List all deployed engines with:
  gcloud alpha ai reasoning-engines list --project ${PROJECT} --region ${REGION}
NEXT
