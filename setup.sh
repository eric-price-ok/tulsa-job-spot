#!/usr/bin/env bash
# =============================================================================
# TulsaJobSpot — Bootstrap Script
# Tested on Ubuntu 24.04 LTS. Run as a non-root user with sudo access.
# =============================================================================
set -euo pipefail

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC}   $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }

echo ""
echo "========================================="
echo "  TulsaJobSpot — Setup"
echo "========================================="
echo ""

# ---------------------------------------------------------------------------
# 1. Docker
# ---------------------------------------------------------------------------
if ! command -v docker &>/dev/null; then
    info "Docker not found — installing..."
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker "$USER"
    warn "Docker installed. You may need to log out and back in for group membership to take effect."
    warn "If the next steps fail with permission denied, run: newgrp docker"
else
    success "Docker $(docker --version | awk '{print $3}' | tr -d ',')"
fi

# ---------------------------------------------------------------------------
# 2. Verify we're in the repo root
# ---------------------------------------------------------------------------
if [ ! -f "docker-compose.yml" ]; then
    echo "Error: Run this script from the repository root directory."
    exit 1
fi

# ---------------------------------------------------------------------------
# 3. .env setup
# ---------------------------------------------------------------------------
if [ ! -f .env ]; then
    info "Creating .env from .env.example..."
    cp .env.example .env

    echo ""
    echo "-----------------------------------------"
    echo "  Configure your deployment"
    echo "-----------------------------------------"

    read -rp "Domain name (e.g. tulsajobspot.com): " DOMAIN_INPUT
    sed -i "s|^DOMAIN=.*|DOMAIN=${DOMAIN_INPUT}|" .env

    # Generate a secure random secret key
    SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${SECRET}|" .env
    success "Generated SECRET_KEY"

    read -rp "Admin email address: " ADMIN_EMAIL_INPUT
    sed -i "s|^ADMIN_EMAIL=.*|ADMIN_EMAIL=${ADMIN_EMAIL_INPUT}|" .env

    echo ""
    echo "OAuth Providers (leave blank to skip):"
    read -rp "  Google Client ID: " GID
    if [ -n "$GID" ]; then
        read -rp "  Google Client Secret: " GSECRET
        sed -i "s|^GOOGLE_CLIENT_ID=.*|GOOGLE_CLIENT_ID=${GID}|" .env
        sed -i "s|^GOOGLE_CLIENT_SECRET=.*|GOOGLE_CLIENT_SECRET=${GSECRET}|" .env
    fi

    echo ""
    warn ".env created. Edit it to add more OAuth providers and SMTP settings."
else
    success ".env already exists — skipping configuration."
fi

# ---------------------------------------------------------------------------
# 4. Start services
# ---------------------------------------------------------------------------
info "Building and starting services..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
success "Services started."

# ---------------------------------------------------------------------------
# 5. Wait for DB to be ready
# ---------------------------------------------------------------------------
info "Waiting for database to be ready..."
for i in $(seq 1 30); do
    if docker compose exec -T db pg_isready -U tulsajobspot >/dev/null 2>&1; then
        success "Database ready."
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "Error: Database did not become ready in time."
        exit 1
    fi
    sleep 2
done

# ---------------------------------------------------------------------------
# 6. Run migrations
# ---------------------------------------------------------------------------
info "Running database migrations..."
docker compose exec app alembic upgrade head
success "Migrations complete."

# ---------------------------------------------------------------------------
# 7. Seed reference data
# ---------------------------------------------------------------------------
info "Seeding reference data..."
docker compose exec app python -m app.scripts.seed
success "Seed data loaded."

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
FINAL_DOMAIN=$(grep "^DOMAIN=" .env | cut -d= -f2)
echo ""
echo "========================================="
echo -e "  ${GREEN}Setup complete!${NC}"
echo "========================================="
echo ""
echo "  Site: https://${FINAL_DOMAIN}"
echo ""
echo "  Next steps:"
echo "    1. Sign in with the admin account (${ADMIN_EMAIL_INPUT:-see .env})"
echo "    2. Enable served cities: Admin → Served Cities"
echo "    3. Configure scraper sources: Admin → Scraper Sources"
echo ""
