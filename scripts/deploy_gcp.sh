#!/usr/bin/env bash
set -euo pipefail

# Build and Deploy ClearCut to Google Cloud Run
# Usage: ./scripts/deploy_gcp.sh [--project <PROJECT_ID>] [--region <REGION>] [--dry-run]

PROJECT_ID="${GCP_PROJECT:-hacksteward}"
REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="clearcut"
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --project)
      PROJECT_ID="$2"
      shift 2
      ;;
    --region)
      REGION="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

SOURCE_SHA="$(git rev-parse HEAD 2>/dev/null || echo "manual")"
SHORT_SOURCE_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo "manual")"

echo "=========================================================="
echo "Starting ClearCut Google Cloud Deploy"
echo "Project:     ${PROJECT_ID}"
echo "Region:      ${REGION}"
echo "Service:     ${SERVICE_NAME}"
echo "Source SHA:  ${SOURCE_SHA}"
echo "=========================================================="

if [ "$DRY_RUN" = true ]; then
  echo "Dry run enabled. Exiting before build submission."
  exit 0
fi

# Set project context
gcloud config set project "${PROJECT_ID}"

# Submit to Cloud Build
echo "Submitting build to Google Cloud Build..."
gcloud builds submit --config=cloudbuild.yaml \
  --substitutions="_PROJECT_ID=${PROJECT_ID},_REGION=${REGION},_SERVICE_NAME=${SERVICE_NAME},COMMIT_SHA=${SOURCE_SHA},SHORT_SHA=${SHORT_SOURCE_SHA}" .

echo "=========================================================="
echo "Deployment Complete!"
echo "Service URL is displayed above in Cloud Run output."
echo "=========================================================="
