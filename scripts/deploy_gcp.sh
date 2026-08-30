#!/usr/bin/env bash
set -euo pipefail

# Build and Deploy ClearCut to Google Cloud Run
# Usage: ./scripts/deploy_gcp.sh [--project <PROJECT_ID>] [--region <REGION>] [--dry-run]

CURRENT_GCP_PROJECT="$(gcloud config get-value project 2>/dev/null || echo "")"
PROJECT_ID="${GCP_PROJECT:-$CURRENT_GCP_PROJECT}"
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

if [ -z "$PROJECT_ID" ]; then
  echo "❌ Error: No Google Cloud project specified. Pass --project <PROJECT_ID> or run 'gcloud config set project <PROJECT_ID>'." >&2
  exit 1
fi

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
echo "Submitting build to Google Cloud Build on project ${PROJECT_ID}..."
gcloud builds submit --config=cloudbuild.yaml \
  --substitutions="_REGION=${REGION},_SERVICE_NAME=${SERVICE_NAME},COMMIT_SHA=${SOURCE_SHA},SHORT_SHA=${SHORT_SOURCE_SHA}" .

echo "=========================================================="
echo "Deployment Complete!"
echo "Service URL is displayed above in Cloud Run output."
echo "=========================================================="
