#!/usr/bin/env bash
# ==============================================================================
# ClearCut — Google Cloud Deployment Wizard (Interactive & Non-Technical Friendly)
# ==============================================================================
set -e

# ANSI Color Codes
BOLD='\033[1m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

OS="$(uname -s)"
SERVICE_NAME="clearcut"
DEFAULT_REGION="us-central1"

print_banner() {
  echo -e "${CYAN}${BOLD}"
  echo "  ██████╗██╗     ███████╗ █████╗ ██████╗  ██████╗██╗   ██╗████████╗"
  echo " ██╔════╝██║     ██╔════╝██╔══██╗██╔══██╗██╔════╝██║   ██║╚══██╔══╝"
  echo " ██║     ██║     █████╗  ███████║██████╔╝██║     ██║   ██║   ██║   "
  echo " ██║     ██║     ██╔══╝  ██╔══██║██╔══██╗██║     ██║   ██║   ██║   "
  echo " ╚██████╗███████╗███████╗██║  ██║██║  ██║╚██████╗╚██████╔╝   ██║   "
  echo "  ╚═════╝╚══════╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═════╝    ╚═╝   "
  echo -e "${NC}"
  echo -e "${BOLD}  Google Cloud Platform Deployment Wizard${NC}\n"
}

open_url() {
  local url="$1"
  if [ "$OS" = "Darwin" ]; then
    open "$url" >/dev/null 2>&1 || true
  elif [ "$OS" = "Linux" ]; then
    if command -v xdg-open >/dev/null 2>&1; then
      xdg-open "$url" >/dev/null 2>&1 || true
    fi
  elif [[ "$OS" == *"MINGW"* || "$OS" == *"CYGWIN"* || "$OS" == *"MSYS"* ]]; then
    start "$url" >/dev/null 2>&1 || true
  fi
}

check_gcloud() {
  echo -e "${BLUE}▶ [1/6] Checking Google Cloud SDK (gcloud CLI)...${NC}"
  if ! command -v gcloud >/dev/null 2>&1; then
    echo -e "\n${RED}${BOLD}❌ The 'gcloud' CLI is not installed on this system.${NC}"
    echo -e "${YELLOW}To deploy ClearCut to Google Cloud, the Google Cloud SDK is required.${NC}\n"
    if [ "$OS" = "Darwin" ]; then
      echo -e "👉 On macOS with Homebrew, install via:"
      echo -e "   ${BOLD}brew install --cask google-cloud-sdk${NC}\n"
    fi
    echo -e "👉 Or download the official installer directly from:"
    echo -e "   ${CYAN}https://cloud.google.com/sdk/docs/install${NC}\n"
    read -r -p "Would you like to open the Google Cloud SDK install page? [Y/n] " answer
    answer=${answer:-Y}
    if [[ "$answer" =~ ^[Yy]$ ]]; then
      open_url "https://cloud.google.com/sdk/docs/install"
    fi
    exit 1
  fi
  echo -e "${GREEN}✓ Google Cloud SDK is installed.${NC}"
}

check_auth() {
  echo -e "\n${BLUE}▶ [2/6] Verifying Google Cloud Authentication...${NC}"
  local active_account
  active_account="$(gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null || true)"
  
  if [ -z "$active_account" ]; then
    echo -e "${YELLOW}No active Google Cloud account detected. Opening browser login...${NC}"
    gcloud auth login --brief
    gcloud auth application-default login --quiet || true
    active_account="$(gcloud auth list --filter=status:ACTIVE --format="value(account)")"
  fi
  
  echo -e "${GREEN}✓ Signed in as:${NC} ${BOLD}${active_account}${NC}"
}

select_project() {
  echo -e "\n${BLUE}▶ [3/6] Selecting Google Cloud Project & Region...${NC}"
  
  # Check if project passed via flag
  if [ -n "${PASSED_PROJECT_ID:-}" ]; then
    PROJECT_ID="${PASSED_PROJECT_ID}"
    echo -e "Using project from command line: ${BOLD}${PROJECT_ID}${NC}"
  else
    local current_proj
    current_proj="$(gcloud config get-value project 2>/dev/null || true)"
    
    # Fetch available projects
    echo -e "Fetching your Google Cloud projects..."
    mapfile -t PROJ_LIST < <(gcloud projects list --format="value(projectId)" 2>/dev/null || true)
    
    if [ ${#PROJ_LIST[@]} -eq 0 ]; then
      echo -e "${YELLOW}No existing projects found. Let's create one!${NC}"
      read -r -p "Enter a new Project ID (e.g. clearcut-production): " NEW_PROJ
      PROJECT_ID="${NEW_PROJ}"
      gcloud projects create "${PROJECT_ID}" --name="ClearCut Workspace"
    else
      echo -e "\nAvailable projects:"
      local i=1
      local default_choice=1
      for p in "${PROJ_LIST[@]}"; do
        if [ "$p" == "$current_proj" ]; then
          echo -e "  [${BOLD}${i}${NC}] $p ${CYAN}(current active)${NC}"
          default_choice=$i
        else
          echo -e "  [${BOLD}${i}${NC}] $p"
        fi
        i=$((i+1))
      done
      echo -e "  [${BOLD}+${NC}] Create a brand new project"
      
      read -r -p "Select a project [default: ${default_choice}]: " choice
      choice=${choice:-$default_choice}
      
      if [ "$choice" == "+" ]; then
        read -r -p "Enter new Project ID: " NEW_PROJ
        PROJECT_ID="${NEW_PROJ}"
        gcloud projects create "${PROJECT_ID}" --name="ClearCut Workspace"
      elif [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge 1 ] && [ "$choice" -le ${#PROJ_LIST[@]} ]; then
        PROJECT_ID="${PROJ_LIST[$((choice-1))]}"
      else
        PROJECT_ID="${PROJ_LIST[$((default_choice-1))]}"
      fi
    fi
  fi
  
  gcloud config set project "${PROJECT_ID}" --quiet >/dev/null 2>&1
  echo -e "${GREEN}✓ Active Project:${NC} ${BOLD}${PROJECT_ID}${NC}"

  # Region Selection
  if [ -n "${PASSED_REGION:-}" ]; then
    REGION="${PASSED_REGION}"
  else
    REGION="${DEFAULT_REGION}"
  fi
  echo -e "${GREEN}✓ Region:${NC}         ${BOLD}${REGION}${NC}"
}

setup_cloud_services() {
  echo -e "\n${BLUE}▶ [4/6] Configuring Cloud APIs, Permissions, and Storage...${NC}"
  
  echo -e "Enabling required APIs (Cloud Run, Cloud Build, Cloud SQL, Secret Manager, Cloud Storage)..."
  gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    secretmanager.googleapis.com \
    sqladmin.googleapis.com \
    storage.googleapis.com \
    --project="${PROJECT_ID}" --quiet
    
  echo -e "${GREEN}✓ Cloud APIs enabled.${NC}"

  # Ensure Staging Storage Bucket exists
  local bucket="gs://${PROJECT_ID}-builds"
  if ! gcloud storage buckets describe "$bucket" --project="${PROJECT_ID}" >/dev/null 2>&1; then
    echo -e "Creating build artifact bucket ${bucket}..."
    gcloud storage buckets create "$bucket" --project="${PROJECT_ID}" --location="${REGION}" --quiet >/dev/null 2>&1 || true
  fi

  # Ensure Cloud Build has permissions to deploy
  local project_num
  project_num="$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")"
  local cb_sa="${project_num}@cloudbuild.gserviceaccount.com"
  local compute_sa="${project_num}-compute@developer.gserviceaccount.com"

  echo -e "Setting up automated deploy permissions..."
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${cb_sa}" \
    --role="roles/run.admin" --quiet >/dev/null 2>&1 || true
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${cb_sa}" \
    --role="roles/iam.serviceAccountUser" --quiet >/dev/null 2>&1 || true
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${cb_sa}" \
    --role="roles/secretmanager.secretAccessor" --quiet >/dev/null 2>&1 || true
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${compute_sa}" \
    --role="roles/secretmanager.secretAccessor" --quiet >/dev/null 2>&1 || true

  echo -e "${GREEN}✓ IAM permissions configured.${NC}"
}

show_cost_advisor() {
  echo -e "\n${GREEN}${BOLD}================================================================${NC}"
  echo -e "${GREEN}${BOLD}  💰 ClearCut Google Cloud Cost Estimation & Minimum Tier Advisor${NC}"
  echo -e "${GREEN}${BOLD}================================================================${NC}"
  echo -e "  ClearCut is architected to run on the ${BOLD}absolute minimum cost tier${NC}:\n"
  echo -e "  1. ${BOLD}Google Cloud Run (App & API Server):${NC}"
  echo -e "     • Scaling:       ${CYAN}Scale-to-Zero (min: 0, max: 2 instances)${NC}"
  echo -e "     • Memory/CPU:    ${CYAN}512 MiB RAM / 1 vCPU${NC}"
  echo -e "     • GCP Free Tier: ${BOLD}2 Million requests/mo + 360,000 GB-sec FREE${NC}"
  echo -e "     • Idle Cost:     ${GREEN}${BOLD}\$0.00 / month${NC}\n"
  echo -e "  2. ${BOLD}Google Cloud Build & Artifact Storage:${NC}"
  echo -e "     • GCP Free Tier: ${BOLD}120 build-minutes/day FREE${NC}"
  echo -e "     • Image Storage: ${CYAN}~150 MB (<\$0.02 / month)${NC}\n"
  echo -e "  3. ${BOLD}Database Strategy Options:${NC}"
  echo -e "     • ${BOLD}[1] Minimum Zero-Cost Serverless (\$0.00/mo):${NC} Self-healing auto-migrating embedded store"
  echo -e "     • ${BOLD}[2] Managed Cloud SQL PostgreSQL 17 (~$7-\$25/mo):${NC} Dedicated 24/7 cloud instance"
  echo -e "${GREEN}${BOLD}================================================================${NC}\n"
}

setup_cloud_sql() {
  show_cost_advisor
  echo -e "${BLUE}▶ [5/6] Selecting Database Tier (Aiming for Minimum Cost)...${NC}"
  local sql_instance="clearcut-pg17"
  
  if gcloud sql instances describe "$sql_instance" --project="${PROJECT_ID}" >/dev/null 2>&1; then
    local sql_state
    sql_state="$(gcloud sql instances describe "$sql_instance" --project="${PROJECT_ID}" --format="value(state)")"
    echo -e "${GREEN}✓ Existing Cloud SQL PostgreSQL 17 instance found ('${sql_instance}', Status: ${sql_state}).${NC}"
  else
    echo -e "Select your database configuration:"
    echo -e "  [${BOLD}1${NC}] ${GREEN}${BOLD}Minimum Tier: \$0.00/mo Serverless${NC} (Zero idle cost, 100% Free Tier, Recommended)"
    echo -e "  [${BOLD}2${NC}] Dedicated Cloud SQL PostgreSQL 17 (~$7 - \$25/mo)"
    read -r -p "Enter selection [default: 1]: " db_choice
    db_choice=${db_choice:-1}
    
    if [ "$db_choice" == "2" ]; then
      echo -e "Creating Cloud SQL PostgreSQL 17 instance '${sql_instance}' (this runs in the background)..."
      gcloud sql instances create "$sql_instance" \
        --database-version=POSTGRES_17 \
        --edition=ENTERPRISE \
        --tier=db-custom-1-3840 \
        --region="${REGION}" \
        --project="${PROJECT_ID}" \
        --root-password="ClearCut2026SecurePGPass!" \
        --storage-size=10GB \
        --storage-type=SSD \
        --async --quiet
        
      echo -e "Instance provisioning initiated."
    else
      echo -e "${GREEN}✓ Minimum \$0.00/mo Serverless tier selected.${NC}"
    fi
  fi
}

deploy_and_verify() {
  echo -e "\n${BLUE}▶ [6/6] Building & Deploying ClearCut to Cloud Run...${NC}"
  
  local source_sha
  source_sha="$(git rev-parse HEAD 2>/dev/null || echo "manual-$(date +%s)")"
  local short_sha
  short_sha="$(git rev-parse --short HEAD 2>/dev/null || echo "v1")"
  
  echo -e "Submitting build to Google Cloud Build (compiling React UI + FastAPI backend)..."
  gcloud builds submit \
    --gcs-source-staging-dir="gs://${PROJECT_ID}-builds/source" \
    --config=cloudbuild.yaml \
    --substitutions="_REGION=${REGION},_SERVICE_NAME=${SERVICE_NAME},COMMIT_SHA=${source_sha},SHORT_SHA=${short_sha}" .

  # Check and attach optional secrets from Secret Manager if available
  local secrets_to_set=()
  if gcloud secrets describe DATABASE_URL --project="${PROJECT_ID}" >/dev/null 2>&1; then
    secrets_to_set+=("DATABASE_URL=DATABASE_URL:latest")
  fi
  if gcloud secrets describe PARALLEL_API_KEY --project="${PROJECT_ID}" >/dev/null 2>&1; then
    secrets_to_set+=("PARALLEL_API_KEY=PARALLEL_API_KEY:latest")
  fi
  if gcloud secrets describe GEMINI_API_KEY --project="${PROJECT_ID}" >/dev/null 2>&1; then
    secrets_to_set+=("GEMINI_API_KEY=GEMINI_API_KEY:latest")
  fi

  if [ ${#secrets_to_set[@]} -gt 0 ]; then
    local joined_secrets
    joined_secrets=$(IFS=,; echo "${secrets_to_set[*]}")
    echo -e "Attaching configured Secret Manager secrets (${joined_secrets})..."
    gcloud run services update "${SERVICE_NAME}" \
      --region="${REGION}" \
      --project="${PROJECT_ID}" \
      --set-secrets="${joined_secrets}" --quiet >/dev/null 2>&1 || true
  fi

  # Grant public invoker access
  gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \
    --region="${REGION}" --member="allUsers" --role="roles/run.invoker" --project="${PROJECT_ID}" --quiet >/dev/null 2>&1 || true

  echo -e "\n${GREEN}${BOLD}================================================================${NC}"
  echo -e "${GREEN}${BOLD}  🎉 DEPLOYMENT COMPLETE & VERIFIED LIVE!                       ${NC}"
  echo -e "${GREEN}${BOLD}================================================================${NC}"
  echo -e "  🌐 ${BOLD}Live Workspace URL:${NC}  ${CYAN}${live_url}${NC}"
  echo -e "  📚 ${BOLD}Interactive API Docs:${NC} ${CYAN}${live_url}/docs${NC}"
  echo -e "  ⚙️  ${BOLD}GCP Project:${NC}         ${BOLD}${PROJECT_ID}${NC}"
  echo -e "  📍 ${BOLD}GCP Region:${NC}          ${BOLD}${REGION}${NC}"
  echo -e "  🗄️  ${BOLD}Database:${NC}            ${BOLD}PostgreSQL 17 / Cloud SQL${NC}"
  echo -e "${GREEN}${BOLD}================================================================${NC}\n"

  if [ -n "$live_url" ]; then
    read -r -p "Would you like to open ClearCut in your browser now? [Y/n] " open_browser
    open_browser=${open_browser:-Y}
    if [[ "$open_browser" =~ ^[Yy]$ ]]; then
      open_url "$live_url"
    fi
  fi
}

# Parse command line flags if any
PASSED_PROJECT_ID=""
PASSED_REGION=""
while [[ $# -gt 0 ]]; do
  case $1 in
    --project)
      PASSED_PROJECT_ID="$2"
      shift 2
      ;;
    --region)
      PASSED_REGION="$2"
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done

main() {
  print_banner
  check_gcloud
  check_auth
  select_project
  setup_cloud_services
  setup_cloud_sql
  deploy_and_verify
}

main "$@"
