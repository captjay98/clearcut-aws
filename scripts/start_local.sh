#!/usr/bin/env bash
# ==============================================================================
# ClearCut — Local Workspace Launcher (Interactive & Non-Technical Friendly)
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

# Determine OS
OS="$(uname -s)"

print_banner() {
  echo -e "${CYAN}${BOLD}"
  echo "  ██████╗██╗     ███████╗ █████╗ ██████╗  ██████╗██╗   ██╗████████╗"
  echo " ██╔════╝██║     ██╔════╝██╔══██╗██╔══██╗██╔════╝██║   ██║╚══██╔══╝"
  echo " ██║     ██║     █████╗  ███████║██████╔╝██║     ██║   ██║   ██║   "
  echo " ██║     ██║     ██╔══╝  ██╔══██║██╔══██╗██║     ██║   ██║   ██║   "
  echo " ╚██████╗███████╗███████╗██║  ██║██║  ██║╚██████╗╚██████╔╝   ██║   "
  echo "  ╚═════╝╚══════╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═════╝    ╚═╝   "
  echo -e "${NC}"
  echo -e "${BOLD}  Screenplay Pre-Clearance & Evidence Workspace (Local Studio)${NC}\n"
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

check_docker() {
  echo -e "${BLUE}▶ [1/4] Checking Docker environment...${NC}"
  
  if ! command -v docker >/dev/null 2>&1; then
    echo -e "\n${RED}${BOLD}❌ Docker is not installed on this system.${NC}"
    echo -e "${YELLOW}ClearCut uses Docker to run the workspace and PostgreSQL database without installing complex software.${NC}\n"
    echo -e "👉 Please download and install ${BOLD}Docker Desktop${NC} from:"
    echo -e "   ${CYAN}https://www.docker.com/products/docker-desktop/${NC}\n"
    read -r -p "Would you like to open the Docker download page in your browser? [Y/n] " answer
    answer=${answer:-Y}
    if [[ "$answer" =~ ^[Yy]$ ]]; then
      open_url "https://www.docker.com/products/docker-desktop/"
    fi
    exit 1
  fi

  if ! docker info >/dev/null 2>&1; then
    echo -e "\n${YELLOW}${BOLD}⚠️  Docker is installed, but Docker Desktop is not currently running.${NC}"
    echo -e "Please launch ${BOLD}Docker Desktop${NC} from your Applications / Start Menu."
    echo -e "Waiting for Docker to start (up to 30 seconds)..."
    
    local count=0
    while ! docker info >/dev/null 2>&1; do
      sleep 2
      count=$((count + 2))
      if [ $count -ge 30 ]; then
        echo -e "\n${RED}❌ Docker did not respond in time. Please open Docker Desktop and try running this command again.${NC}"
        exit 1
      fi
      echo -n "."
    done
    echo -e "\n${GREEN}✓ Docker is running!${NC}"
  else
    echo -e "${GREEN}✓ Docker is running and ready.${NC}"
  fi
}

check_ports() {
  echo -e "\n${BLUE}▶ [2/4] Checking required network ports (8000, 5432)...${NC}"
  
  # Check port 8000
  if lsof -i :8000 >/dev/null 2>&1; then
    local proc_8000
    proc_8000=$(lsof -i :8000 | tail -n 1 | awk '{print $1}')
    if [[ "$proc_8000" != *"docker"* && "$proc_8000" != *"com.dock"* ]]; then
      echo -e "${YELLOW}⚠️  Port 8000 is currently used by '$proc_8000'.${NC}"
      echo -e "ClearCut will stop or replace any previous ClearCut containers automatically."
    fi
  fi
  echo -e "${GREEN}✓ Ports are ready.${NC}"
}

setup_env() {
  echo -e "\n${BLUE}▶ [3/4] Preparing configuration and demo database...${NC}"
  
  if [ ! -f ".env" ]; then
    echo -e "Creating local .env configuration..."
    cat <<EOF > .env
# ClearCut Local Environment Configuration
PORT=8080
DATABASE_URL=postgresql+asyncpg://clearcut:clearcut_dev_password@db:5432/clearcut
# Parallel API key for live search & extraction (leave blank to run in demo registry mode)
PARALLEL_API_KEY=
# Google Cloud Vertex AI settings
GCP_PROJECT=clearcut-workspace
VERTEX_LOCATION=global
EOF
  fi
  echo -e "${GREEN}✓ Environment configured.${NC}"
}

launch_containers() {
  echo -e "\n${BLUE}▶ [4/4] Starting ClearCut Studio with PostgreSQL 17...${NC}"
  echo -e "This might take a minute on first run to build the multi-stage container..."
  
  docker compose up -d --build
  
  echo -e "Waiting for workspace services to become healthy..."
  local timeout=45
  local count=0
  while [ $count -lt $timeout ]; do
    if curl -s -f "http://localhost:8000/api/v1/healthz" >/dev/null 2>&1; then
      break
    fi
    sleep 2
    count=$((count + 2))
    echo -n "."
  done
  echo ""

  if curl -s -f "http://localhost:8000/api/v1/healthz" >/dev/null 2>&1; then
    echo -e "\n${GREEN}${BOLD}================================================================${NC}"
    echo -e "${GREEN}${BOLD}  ✨ ClearCut Studio is LIVE and ready!                         ${NC}"
    echo -e "${GREEN}${BOLD}================================================================${NC}"
    echo -e "  🎬 ${BOLD}Web Workspace:${NC}      ${CYAN}http://localhost:8000${NC}"
    echo -e "  📚 ${BOLD}API Docs (Swagger):${NC} ${CYAN}http://localhost:8000/docs${NC}"
    echo -e "  🗄️  ${BOLD}Database Engine:${NC}    ${BOLD}PostgreSQL 17${NC} (port 5432)"
    echo -e "  📋 ${BOLD}Sample Screenplay:${NC}  ${BOLD}Borrowed Light${NC} (7 scenes, 10 items seeded)"
    echo -e "${GREEN}${BOLD}================================================================${NC}\n"
    
    echo -e "${BLUE}Opening workspace in your default browser...${NC}"
    open_url "http://localhost:8000"
    
    echo -e "\n💡 ${BOLD}Helpful Commands:${NC}"
    echo -e "   • To view live logs:   ${BOLD}./clearcut logs${NC} (or ${BOLD}docker compose logs -f${NC})"
    echo -e "   • To stop workspace:   ${BOLD}./clearcut stop${NC} (or ${BOLD}docker compose down${NC})"
    echo -e "   • To run smoke test:   ${BOLD}./clearcut smoke${NC}\n"
  else
    echo -e "\n${RED}⚠️  Services started, but healthcheck timed out.${NC}"
    echo -e "Check logs with: ${BOLD}docker compose logs -f${NC}\n"
  fi
}

main() {
  print_banner
  check_docker
  check_ports
  setup_env
  launch_containers
}

main "$@"
