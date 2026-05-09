#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-${ROOT_DIR}/.env}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing env file: ${ENV_FILE}" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

PROJECT_ID="${PROJECT_ID:-${GCP_PROJECT_ID:?GCP_PROJECT_ID is required in .env}}"
REGION="${REGION:-${GCP_REGION:-us-central1}}"
REPOSITORY="${REPOSITORY:-cognizinterview}"
BACKEND_SERVICE="${BACKEND_SERVICE:-cogniz-graphrag-api}"
FRONTEND_SERVICE="${FRONTEND_SERVICE:-cogniz-graphrag-web}"
CLOUD_SQL_CONNECTION_NAME="${CLOUD_SQL_CONNECTION_NAME:-${CLOUD_SQL_INSTANCE_CONNECTION_NAME:?CLOUD_SQL_INSTANCE_CONNECTION_NAME is required in .env}}"
PROJECT_NUMBER="${PROJECT_NUMBER:-$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')}"
RUN_SERVICE_ACCOUNT="${RUN_SERVICE_ACCOUNT:-${PROJECT_NUMBER}-compute@developer.gserviceaccount.com}"

DATABASE_URL_FOR_CLOUD_RUN="${DATABASE_URL_FOR_CLOUD_RUN:-${DATABASE_URL_CLOUD_RUN:?DATABASE_URL_CLOUD_RUN is required in .env}}"
NEXT_PUBLIC_DEMO_API_KEY_FOR_BUILD="${NEXT_PUBLIC_DEMO_API_KEY:-${API_AUTH_KEY:?API_AUTH_KEY is required in .env}}"
GEMINI_API_KEY_VALUE="${GEMINI_API_KEY:-${gemini_api_key:-}}"
CLOUD_RUN_GRAPH_STORE_BACKEND="${CLOUD_RUN_GRAPH_STORE_BACKEND:-sql}"

TAG="${TAG:-$(date +%Y%m%d%H%M%S)}"
BACKEND_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/backend:${TAG}"
FRONTEND_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/frontend:${TAG}"

GENERATED_DIR="${ROOT_DIR}/deploy/cloudrun/generated"
mkdir -p "${GENERATED_DIR}"

BACKEND_ENV_INITIAL="${GENERATED_DIR}/backend.initial.env.yaml"
BACKEND_ENV_FINAL="${GENERATED_DIR}/backend.final.env.yaml"
FRONTEND_ENV="${GENERATED_DIR}/frontend.env.yaml"

write_backend_env() {
  local output="$1"
  local cors_origin="$2"
  cat >"${output}" <<EOF
APP_ENV: "cloud"
STORE_BACKEND: "${STORE_BACKEND:-sql}"
GRAPH_STORE_BACKEND: "${CLOUD_RUN_GRAPH_STORE_BACKEND}"
CORS_ALLOWED_ORIGINS: "${cors_origin}"
DATABASE_URL: "${DATABASE_URL_FOR_CLOUD_RUN}"
NEO4J_URI: "${NEO4J_URI:?NEO4J_URI is required in .env}"
NEO4J_USERNAME: "${NEO4J_USERNAME:?NEO4J_USERNAME is required in .env}"
GCS_BUCKET_RAW: "${GCS_BUCKET_RAW:?GCS_BUCKET_RAW is required in .env}"
GCS_BUCKET_ARTIFACTS: "${GCS_BUCKET_ARTIFACTS:?GCS_BUCKET_ARTIFACTS is required in .env}"
GCP_PROJECT_ID: "${PROJECT_ID}"
GCP_REGION: "${REGION}"
PARSER_PRIMARY: "${PARSER_PRIMARY:-llamaparse}"
PARSER_FALLBACK: "${PARSER_FALLBACK:-liteparse}"
LLAMAPARSE_TIER: "${LLAMAPARSE_TIER:-agentic}"
LLAMAPARSE_RESULT_TYPE: "${LLAMAPARSE_RESULT_TYPE:-markdown}"
LITEPARSE_OCR_ENABLED: "${LITEPARSE_OCR_ENABLED:-false}"
LITEPARSE_DPI: "${LITEPARSE_DPI:-150}"
ROUTER_MODEL: "${ROUTER_MODEL:-gpt-5.4-mini}"
EXTRACTOR_MODEL: "${EXTRACTOR_MODEL:-gpt-5.4-mini}"
ANSWER_MODEL: "${ANSWER_MODEL:-gpt-5.4-mini}"
GREETING_MODEL: "${GREETING_MODEL:-gpt-5.4-mini}"
LLM_ANSWER_ENABLED: "${LLM_ANSWER_ENABLED:-true}"
ROUTER_REASONING_EFFORT: "${ROUTER_REASONING_EFFORT:-none}"
ANSWER_REASONING_EFFORT: "${ANSWER_REASONING_EFFORT:-low}"
EXTRACTOR_REASONING_EFFORT: "${EXTRACTOR_REASONING_EFFORT:-low}"
PROMPT_CACHE_NAMESPACE: "${PROMPT_CACHE_NAMESPACE:-cognizinterview-graphrag-v1}"
ANSWER_MAX_OUTPUT_TOKENS: "${ANSWER_MAX_OUTPUT_TOKENS:-900}"
EMBEDDING_PROVIDER: "${EMBEDDING_PROVIDER:-gemini_api}"
EMBEDDING_MODEL: "${EMBEDDING_MODEL:-gemini-embedding-2}"
EMBEDDING_DIMENSION: "${EMBEDDING_DIMENSION:-1536}"
EMBEDDING_TASK_TYPE: "${EMBEDDING_TASK_TYPE:-RETRIEVAL_DOCUMENT}"
RERANK_PROVIDER: "${RERANK_PROVIDER:-vertex}"
RERANK_MODEL: "${RERANK_MODEL:-semantic-ranker-default-004}"
RERANK_LOCATION: "${RERANK_LOCATION:-global}"
RERANK_TOP_N: "${RERANK_TOP_N:-8}"
RERANK_CANDIDATE_LIMIT: "${RERANK_CANDIDATE_LIMIT:-40}"
EOF
}

write_frontend_env() {
  local output="$1"
  local backend_url="$2"
  cat >"${output}" <<EOF
NEXT_PUBLIC_API_BASE_URL: "${backend_url}"
NEXT_PUBLIC_DEMO_API_KEY: "${NEXT_PUBLIC_DEMO_API_KEY_FOR_BUILD}"
EOF
}

upsert_secret() {
  local name="$1"
  local value="$2"
  if [[ -z "${value}" ]]; then
    echo "Secret ${name} has an empty value" >&2
    exit 1
  fi
  if gcloud secrets describe "${name}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
    printf '%s' "${value}" | gcloud secrets versions add "${name}" --data-file=- >/dev/null
  else
    printf '%s' "${value}" | gcloud secrets create "${name}" --replication-policy automatic --data-file=- >/dev/null
  fi
}

deploy_backend() {
  local env_file="$1"
  gcloud run deploy "${BACKEND_SERVICE}" \
    --image "${BACKEND_IMAGE}" \
    --region "${REGION}" \
    --platform managed \
    --allow-unauthenticated \
    --service-account "${RUN_SERVICE_ACCOUNT}" \
    --env-vars-file "${env_file}" \
    --set-secrets API_AUTH_KEY=api-auth-key:latest,OPENAI_API_KEY=openai-api-key:latest,GEMINI_API_KEY=gemini-api-key:latest,LLAMA_CLOUD_API_KEY=llama-cloud-api-key:latest,NEO4J_PASSWORD=neo4j-password:latest \
    --add-cloudsql-instances "${CLOUD_SQL_CONNECTION_NAME}" \
    --memory 2Gi \
    --cpu 2 \
    --timeout 900 \
    --concurrency 10 \
    --min-instances 0 \
    --max-instances 2
}

grant_runtime_access() {
  local member="serviceAccount:${RUN_SERVICE_ACCOUNT}"
  local project_roles=(
    "roles/cloudsql.client"
    "roles/storage.objectAdmin"
    "roles/aiplatform.user"
    "roles/discoveryengine.viewer"
  )

  for role in "${project_roles[@]}"; do
    gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
      --member "${member}" \
      --role "${role}" \
      --quiet >/dev/null
  done

  for secret_name in api-auth-key openai-api-key gemini-api-key llama-cloud-api-key neo4j-password; do
    gcloud secrets add-iam-policy-binding "${secret_name}" \
      --project "${PROJECT_ID}" \
      --member "${member}" \
      --role "roles/secretmanager.secretAccessor" \
      --quiet >/dev/null
  done
}

gcloud config set project "${PROJECT_ID}" >/dev/null

gcloud services enable \
  artifactregistry.googleapis.com \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com \
  aiplatform.googleapis.com \
  discoveryengine.googleapis.com \
  storage.googleapis.com

gcloud artifacts repositories describe "${REPOSITORY}" \
  --location "${REGION}" >/dev/null 2>&1 \
  || gcloud artifacts repositories create "${REPOSITORY}" \
    --repository-format docker \
    --location "${REGION}" \
    --description "CognizInterview Graph RAG demo images"

upsert_secret "api-auth-key" "${API_AUTH_KEY:?API_AUTH_KEY is required in .env}"
upsert_secret "openai-api-key" "${OPENAI_API_KEY:?OPENAI_API_KEY is required in .env}"
upsert_secret "gemini-api-key" "${GEMINI_API_KEY_VALUE:?GEMINI_API_KEY or gemini_api_key is required in .env}"
upsert_secret "llama-cloud-api-key" "${LLAMA_CLOUD_API_KEY:?LLAMA_CLOUD_API_KEY is required in .env}"
upsert_secret "neo4j-password" "${NEO4J_PASSWORD:?NEO4J_PASSWORD is required in .env}"
grant_runtime_access

write_backend_env "${BACKEND_ENV_INITIAL}" ""

gcloud builds submit "${ROOT_DIR}" \
  --config "${ROOT_DIR}/deploy/cloudrun/cloudbuild.backend.yaml" \
  --substitutions "_BACKEND_IMAGE=${BACKEND_IMAGE}"

deploy_backend "${BACKEND_ENV_INITIAL}"

BACKEND_URL="$(gcloud run services describe "${BACKEND_SERVICE}" --region "${REGION}" --format 'value(status.url)')"
write_frontend_env "${FRONTEND_ENV}" "${BACKEND_URL}"

gcloud builds submit "${ROOT_DIR}" \
  --config "${ROOT_DIR}/deploy/cloudrun/cloudbuild.frontend.yaml" \
  --substitutions "_FRONTEND_IMAGE=${FRONTEND_IMAGE},_NEXT_PUBLIC_API_BASE_URL=${BACKEND_URL},_NEXT_PUBLIC_DEMO_API_KEY=${NEXT_PUBLIC_DEMO_API_KEY_FOR_BUILD}"

gcloud run deploy "${FRONTEND_SERVICE}" \
  --image "${FRONTEND_IMAGE}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --service-account "${RUN_SERVICE_ACCOUNT}" \
  --env-vars-file "${FRONTEND_ENV}" \
  --memory 1Gi \
  --cpu 1 \
  --timeout 300 \
  --concurrency 20 \
  --min-instances 0 \
  --max-instances 2

FRONTEND_URL="$(gcloud run services describe "${FRONTEND_SERVICE}" --region "${REGION}" --format 'value(status.url)')"
FRONTEND_REGIONAL_URL="https://${FRONTEND_SERVICE}-${PROJECT_NUMBER}.${REGION}.run.app"
FRONTEND_CORS_ORIGINS="${FRONTEND_URL},${FRONTEND_REGIONAL_URL}"
write_backend_env "${BACKEND_ENV_FINAL}" "${FRONTEND_CORS_ORIGINS}"
deploy_backend "${BACKEND_ENV_FINAL}"

cat <<EOF

Deployment complete.

Backend:  ${BACKEND_URL}
Frontend: ${FRONTEND_URL}

Generated env files:
  ${BACKEND_ENV_INITIAL}
  ${BACKEND_ENV_FINAL}
  ${FRONTEND_ENV}

Smoke:
  source "${ENV_FILE}" && curl -H "x-api-key: \${API_AUTH_KEY}" "${BACKEND_URL}/v1/chat/ready"
  source "${ENV_FILE}" && curl -H "x-api-key: \${API_AUTH_KEY}" "${BACKEND_URL}/v1/traces/admin/smoke"
  open "${FRONTEND_URL}"
EOF
