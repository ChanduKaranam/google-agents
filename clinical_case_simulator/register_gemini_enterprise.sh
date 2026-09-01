#!/usr/bin/env bash
# Register a deployed Agent Runtime agent with a Gemini Enterprise app.
#
#   PROJECT=ge-standard-trail APP_ID=your-app_123 \
#   REASONING_ENGINE=projects/.../locations/us-central1/reasoningEngines/123 \
#   ./register_gemini_enterprise.sh
#
# Omit APP_ID and the script lists the apps in the project and stops, so you
# can see what you are about to publish into.
#
# This makes the agent visible to every user of that Gemini Enterprise app.
set -euo pipefail

# Prefer the project venv when one exists, so `python` and `adk` are the ones
# the case bank and tests were verified against.
if [[ -x "$(dirname "$0")/.venv/bin/python" ]]; then
  PATH="$(cd "$(dirname "$0")/.venv/bin" && pwd):${PATH}"
  export PATH
fi

PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
ENDPOINT_LOCATION="${ENDPOINT_LOCATION:-global}"
export DISPLAY_NAME="${DISPLAY_NAME:-Clinical Case Simulator}"
export DESCRIPTION="${DESCRIPTION:-Practise clinical reasoning with an AI virtual patient. Take a history, examine, investigate, build a differential and get a scored performance report. Educational simulation only, not clinical advice.}"

if [[ -z "${PROJECT}" ]]; then
  echo "No project set. Run: gcloud config set project YOUR_PROJECT" >&2
  exit 1
fi

host() {
  if [[ "${ENDPOINT_LOCATION}" == "global" ]]; then
    echo "https://discoveryengine.googleapis.com"
  else
    echo "https://${ENDPOINT_LOCATION}-discoveryengine.googleapis.com"
  fi
}

TOKEN="$(gcloud auth print-access-token)"
BASE="$(host)/v1alpha/projects/${PROJECT}/locations/global/collections/default_collection/engines"

if [[ -z "${APP_ID:-}" ]]; then
  echo "Gemini Enterprise apps in ${PROJECT}:"
  curl -sf -H "Authorization: Bearer ${TOKEN}" -H "X-Goog-User-Project: ${PROJECT}" "${BASE}" \
    | python -c "
import json,sys
for e in json.load(sys.stdin).get('engines', []):
    print('  ', e['name'].rsplit('/',1)[-1], '  --  ', e.get('displayName'))
"
  echo
  echo "Re-run with APP_ID set to the one you want."
  exit 0
fi

if [[ -z "${REASONING_ENGINE:-}" ]]; then
  echo "REASONING_ENGINE is required, e.g." >&2
  echo "  projects/${PROJECT}/locations/us-central1/reasoningEngines/123456" >&2
  exit 1
fi

export REASONING_ENGINE
BODY="$(python - <<PY
import json, os
print(json.dumps({
    "displayName": os.environ["DISPLAY_NAME"],
    "description": os.environ["DESCRIPTION"],
    "adkAgentDefinition": {
        "provisionedReasoningEngine": {
            "reasoningEngine": os.environ["REASONING_ENGINE"]
        }
    },
}))
PY
)"

echo "==> Registering '${DISPLAY_NAME}' with app ${APP_ID}"
curl -sf -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -H "X-Goog-User-Project: ${PROJECT}" \
  "${BASE}/${APP_ID}/assistants/default_assistant/agents" \
  -d "${BODY}" \
  | python -m json.tool

cat <<NEXT

Registered. The agent appears in the Gemini Enterprise app's agent list.

To list agents:
  curl -s -H "Authorization: Bearer \$(gcloud auth print-access-token)" \\
    -H "X-Goog-User-Project: ${PROJECT}" \\
    "${BASE}/${APP_ID}/assistants/default_assistant/agents"

To remove it, DELETE the agent resource name returned above.
NEXT
