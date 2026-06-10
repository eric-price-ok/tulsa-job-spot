# TulsaJobSpot — Deployment Runbook

## Overview

This runbook covers everything needed to deploy TulsaJobSpot on a fresh Ubuntu 24.04 LTS VPS. It is written for the person deploying their own community instance, not just the original Tulsa deployment. If you are forking this project for a different city or community, the steps are identical — only your `.env` values change.

Estimated time from zero to running: **15–30 minutes**, depending on DNS propagation.

---

## Prerequisites

Before you start, you need:

1. **A VPS running Ubuntu 24.04 LTS**
   - Minimum 1GB RAM, 1 vCPU (works but tight)
   - Recommended 2GB RAM, 2 vCPU for comfortable operation with Selenium scrapers
   - 20GB disk minimum; 40GB recommended if you plan to run scrapers at scale
   - Popular providers: DigitalOcean, Linode/Akamai, Hetzner, Vultr, AWS Lightsail
   - Hetzner CX22 (2 vCPU, 4GB RAM, €4/month) is the sweet spot for cost

2. **Root or sudo access to the VPS**

3. **A domain name pointed at the VPS**
   - An A record pointing your domain (e.g. `tulsajobspot.com`) to your VPS IP address
   - If using a subdomain (e.g. `jobs.yourcity.com`), an A record for that subdomain
   - DNS changes can take up to 48 hours to propagate; 15–30 minutes is typical
   - Caddy will not be able to provision a TLS certificate until DNS resolves

4. **At least one OAuth provider configured** (see OAuth Setup section)
   - Google is the easiest to set up and covers most users
   - You need a Client ID and Client Secret before the site is usable

5. **An SMTP provider** for transactional email
   - Options: Mailgun (free tier), SendGrid, AWS SES, Postmark, or your own Postfix
   - You need SMTP credentials before approval notifications will work
   - The site will function without email but the workflow queues will be silent

6. **An Anthropic API key** (for scraper AI extraction)
   - Required if you plan to use the scraper pipeline
   - Optional if you're running a posting-only board with no scrapers
   - Get one at https://console.anthropic.com

---

## VPS Initial Setup

These steps harden the server before deploying the application. Run all commands as root or with `sudo`.

### 1. Update the system

```bash
apt update && apt upgrade -y
```

### 2. Set the hostname

```bash
hostnamectl set-hostname tulsajobspot
```

Edit `/etc/hosts` and add your domain alongside the hostname:
```
127.0.1.1   tulsajobspot tulsajobspot.com
```

### 3. Create a non-root deploy user

Running the application as root is a security risk. Create a dedicated user:

```bash
adduser deploy
usermod -aG sudo deploy
```

Copy your SSH key to the new user:
```bash
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy
```

From this point forward, all commands run as the `deploy` user unless noted.

```bash
su - deploy
```

### 4. Configure the firewall

Ubuntu 24.04 ships with `ufw`. Enable it with only the ports we need:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

Expected output:
```
Status: active
To                         Action      From
--                         ------      ----
OpenSSH                    ALLOW       Anywhere
80/tcp                     ALLOW       Anywhere
443/tcp                    ALLOW       Anywhere
```

**Do not open port 5432 (Postgres) or 6379 (Redis).** Those services communicate only within Docker's internal network.

### 5. Set the timezone

```bash
sudo timedatectl set-timezone America/Chicago
```

Replace `America/Chicago` with your local timezone. Run `timedatectl list-timezones` to find yours. This affects log timestamps and scheduled job timing.

### 6. Configure automatic security updates

```bash
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure --priority=low unattended-upgrades
```

Accept the defaults. This keeps security patches applied automatically.

### 7. Install fail2ban

Protects against SSH brute force:

```bash
sudo apt install -y fail2ban
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

---

## Install Docker

Ubuntu 24.04 requires installing Docker from Docker's official repository. Do not use the `docker.io` package from Ubuntu's repos — it is outdated.

```bash
# Install prerequisites
sudo apt install -y ca-certificates curl gnupg

# Add Docker's GPG key
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Add Docker repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Add deploy user to docker group (avoids needing sudo for docker commands)
sudo usermod -aG docker deploy

# Apply group membership without logging out
newgrp docker

# Verify
docker --version
docker compose version
```

Expected output (versions may differ):
```
Docker version 26.x.x, build xxxxxxx
Docker Compose version v2.x.x
```

---

## OAuth Provider Setup

You need at least one provider. Google is recommended as the default.

### Google OAuth

1. Go to https://console.cloud.google.com
2. Create a new project (or use an existing one)
3. Navigate to **APIs & Services → Credentials**
4. Click **Create Credentials → OAuth 2.0 Client ID**
5. Application type: **Web application**
6. Name: `TulsaJobSpot` (or your site name)
7. Authorized redirect URIs: `https://yourdomain.com/auth/google/callback`
8. Click **Create**
9. Copy the **Client ID** and **Client Secret** — you'll need these for `.env`

Note: Google will show your app as "unverified" until you complete their verification process. This is fine for initial deployment; users will see a warning screen but can still sign in.

### LinkedIn OAuth

1. Go to https://developer.linkedin.com/apps
2. Click **Create App**
3. Fill in app name, LinkedIn page (create one if needed), logo
4. Under **Auth**, add redirect URL: `https://yourdomain.com/auth/linkedin/callback`
5. Under **Products**, request access to **Sign In with LinkedIn using OpenID Connect**
6. Copy **Client ID** and **Client Secret**

### GitHub OAuth

1. Go to https://github.com/settings/applications/new
2. Application name: your site name
3. Homepage URL: `https://yourdomain.com`
4. Authorization callback URL: `https://yourdomain.com/auth/github/callback`
5. Click **Register application**
6. Click **Generate a new client secret**
7. Copy **Client ID** and **Client Secret**

### Microsoft OAuth

1. Go to https://portal.azure.com → **Azure Active Directory → App registrations**
2. Click **New registration**
3. Name your app, select **Accounts in any organizational directory and personal Microsoft accounts**
4. Redirect URI: `https://yourdomain.com/auth/microsoft/callback`
5. After creation, go to **Certificates & secrets → New client secret**
6. Copy **Application (client) ID** and the secret **Value**

---

## Deploy the Application

### 1. Clone the repository

```bash
cd /home/deploy
git clone https://github.com/eric-price-ok/tulsa-job-spot.git tulsajobspot
cd tulsajobspot
```

### 2. Configure environment variables

```bash
cp .env.example .env
nano .env
```

Fill in all required values. See the full variable reference below.

### 3. Run the bootstrap script

```bash
chmod +x setup.sh
./setup.sh
```

The script will:
1. Validate that required `.env` values are set
2. Build the Docker images
3. Start all services (`app`, `worker`, `db`, `redis`, `caddy`)
4. Wait for the database to be ready
5. Run Alembic migrations
6. Seed reference data (countries, states, cities, job types, functions, etc.)
7. Create the admin user record based on `ADMIN_EMAIL`
8. Print the site URL and confirm it's reachable

If anything fails, the script prints which step failed and exits cleanly. Services are left running so you can inspect logs.

### 4. Verify the deployment

```bash
# Check all services are running
docker compose ps

# Expected: all services showing "running" or "healthy"

# Tail application logs
docker compose logs -f app

# Check Caddy got a TLS certificate
docker compose logs caddy | grep "certificate"
```

Visit `https://yourdomain.com` in a browser. You should see the job board home page with a valid HTTPS certificate.

### 5. Sign in as admin

1. Click Sign In and authenticate with the OAuth provider matching your `ADMIN_EMAIL`
2. Verify your account shows admin access (Admin link visible in nav)
3. Go to Admin → Cities and enable the cities your board serves
4. Go to Admin → Site Config and set your site name and contact email

---

## Production vs Development Compose Files

The repository ships two Docker Compose files:

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Base configuration. Used for local development — includes `--reload`, bind-mounted source code, and exposed DB/Redis ports for local access. |
| `docker-compose.prod.yml` | Production overrides. Replaces `--reload` uvicorn with gunicorn (4 workers), removes the bind mount (container runs from the baked image), closes the DB/Redis ports, and adds `restart: unless-stopped` to all services. |

On the production server, `.env` contains `COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml`. Docker Compose reads this variable and automatically layers both files for every `docker compose` command — no `-f` flags needed. The initial `setup.sh` bootstrap adds this entry automatically for new installs.

**Existing server:** If your `.env` does not yet have `COMPOSE_FILE`, add this line and then rebuild:

```bash
echo "COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml" >> .env
docker compose up -d --build
```

---

## Environment Variable Reference

All variables live in `.env` in the project root. Never commit this file to git — it is in `.gitignore`.

### Required

| Variable | Description | Example |
|---|---|---|
| `DOMAIN` | Your domain name, no protocol | `tulsajobspot.com` |
| `SECRET_KEY` | Random 64-character string for signing sessions | See generation command below |
| `DATABASE_URL` | Postgres connection string | `postgresql://tjsuser:password@db:5432/tulsajobspot` |
| `POSTGRES_PASSWORD` | Postgres password (used by docker compose to init db) | `a-strong-password` |
| `REDIS_URL` | Redis connection string | `redis://redis:6379` |
| `ADMIN_EMAIL` | Email address of first admin account | `you@example.com` |
| `SMTP_HOST` | SMTP server hostname | `smtp.mailgun.org` |
| `SMTP_PORT` | SMTP port | `587` |
| `SMTP_USER` | SMTP username | `postmaster@mg.yourdomain.com` |
| `SMTP_PASSWORD` | SMTP password | |
| `SMTP_FROM` | From address for outgoing email | `noreply@yourdomain.com` |

Generate a secure `SECRET_KEY`:
```bash
openssl rand -hex 32
```

### OAuth (add only providers you want enabled)

| Variable | Description |
|---|---|
| `GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret |
| `LINKEDIN_CLIENT_ID` | LinkedIn OAuth client ID |
| `LINKEDIN_CLIENT_SECRET` | LinkedIn OAuth client secret |
| `GITHUB_CLIENT_ID` | GitHub OAuth client ID |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth client secret |
| `MICROSOFT_CLIENT_ID` | Microsoft OAuth client ID |
| `MICROSOFT_CLIENT_SECRET` | Microsoft OAuth client secret |
| `FACEBOOK_CLIENT_ID` | Facebook OAuth client ID |
| `FACEBOOK_CLIENT_SECRET` | Facebook OAuth client secret |

### Optional

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required for scraper AI extraction; omit if not using scrapers |
| `APP_WORKERS` | `2` | Number of Gunicorn workers. Set to `(2 × CPU cores) + 1` |
| `LOG_LEVEL` | `info` | App log level: `debug`, `info`, `warning`, `error` |
| `SELENIUM_REMOTE_URL` | — | Remote Selenium Grid URL if not running Chrome locally |

---

## Ongoing Operations

### View logs

```bash
# All services
docker compose logs -f

# Single service
docker compose logs -f app
docker compose logs -f worker
docker compose logs -f caddy
```

### Restart a service

```bash
docker compose restart app
docker compose restart worker
```

### Restart everything

```bash
docker compose down && docker compose up -d
```

### Update to a new version

```bash
cd /home/deploy/tulsajobspot
git pull
docker compose up -d --build
docker compose exec app alembic upgrade head
```

`--build` is required because `docker-compose.prod.yml` removes the bind mount — the container runs from the baked image, so a new image must be built to pick up code changes. Alembic will apply any new migrations; if a migration fails it rolls back automatically.

If you have not yet added `COMPOSE_FILE` to your `.env` (see below), use the explicit form instead:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

### Run a migration manually

```bash
docker compose exec app alembic upgrade head
```

### Access the database directly

```bash
docker compose exec db psql -U tjsuser -d tulsajobspot
```

### Database backup

Manual backup:
```bash
docker compose exec db pg_dump -U tjsuser tulsajobspot > backup_$(date +%Y%m%d_%H%M%S).sql
```

Automated nightly backup — add to `/home/deploy/tulsajobspot/scripts/backup.sh`:
```bash
#!/bin/bash
BACKUP_DIR=/home/deploy/backups
mkdir -p $BACKUP_DIR
docker compose -f /home/deploy/tulsajobspot/docker-compose.yml exec -T db \
  pg_dump -U tjsuser tulsajobspot > $BACKUP_DIR/backup_$(date +%Y%m%d).sql
# Keep last 30 days
find $BACKUP_DIR -name "backup_*.sql" -mtime +30 -delete
```

Add to crontab (`crontab -e`):
```
0 2 * * * /home/deploy/tulsajobspot/scripts/backup.sh
```

This is a local backup only. For production, pipe the output to S3, Backblaze B2, or another offsite location.

### Database restore

```bash
docker compose exec -T db psql -U tjsuser tulsajobspot < backup_20250101_020000.sql
```

### Check background worker health

```bash
# See what jobs the worker has processed
docker compose logs worker | tail -100

# Trigger a manual scraper run (from the admin UI, or via CLI)
docker compose exec worker python -m app.workers.scraper run --source-id 1
```

### Monitor disk usage

```bash
df -h
docker system df
```

Docker images and volumes accumulate over time. Clean up unused images:
```bash
docker image prune -f
```

---

## Troubleshooting

### Site not reachable after deployment

1. Confirm DNS has propagated: `dig yourdomain.com` — should return your VPS IP
2. Check Caddy logs: `docker compose logs caddy`
3. Check firewall: `sudo ufw status` — ports 80 and 443 must be open
4. Some VPS providers have a separate firewall in their control panel — check there too

### TLS certificate not provisioning

Caddy uses Let's Encrypt. Common causes of failure:
- DNS not yet pointing to this server (most common — wait and retry)
- Port 80 blocked (Let's Encrypt uses HTTP-01 challenge)
- Rate limited by Let's Encrypt (too many certificate requests for this domain)

Check: `docker compose logs caddy | grep -i "error\|certificate\|tls"`

### OAuth sign-in fails

1. Check that redirect URI in your OAuth provider console exactly matches `https://yourdomain.com/auth/{provider}/callback`
2. Confirm `CLIENT_ID` and `CLIENT_SECRET` are correctly set in `.env`
3. Check app logs: `docker compose logs app | grep -i "oauth\|auth"`

### Database connection errors

```bash
# Check postgres is running and healthy
docker compose ps db

# Check connection from app container
docker compose exec app python -c "from app.database import engine; print(engine.connect())"
```

### Worker not processing jobs

```bash
docker compose logs worker | tail -50
# Look for "Connected to Redis" on startup
# If not present, check REDIS_URL in .env
```

### Out of disk space

```bash
# Find large files
du -sh /home/deploy/tulsajobspot/*
du -sh /var/lib/docker

# Clean Docker
docker system prune -f
docker volume prune -f  # WARNING: only if you've backed up first
```

---

## Security Notes

- Never expose ports 5432 or 6379 to the internet
- Rotate `SECRET_KEY` if you suspect it has been compromised (invalidates all sessions)
- Keep `ADMIN_EMAIL` set to an email you actually control
- Review OAuth app permissions periodically in each provider's console
- Keep the VPS updated: `sudo apt update && sudo apt upgrade -y` monthly at minimum
- The AGPL-3.0 license requires that if you modify and run this software as a network service, you must make your modifications available. This applies to you too if you fork.

---

## Forking for a New Community

If you're deploying this for a different city or region:

1. Fork the repository on GitHub
2. Follow this runbook on your own VPS
3. In `.env`, set `DOMAIN` to your domain and `ADMIN_EMAIL` to your email
4. After first login, go to Admin → Site Config and update:
   - Site name (e.g. "OKC Job Spot")
   - Site tagline
   - Contact email
5. Go to Admin → Cities and enable the cities your board serves
6. Optional: configure scraper sources for employers in your area

No code changes required. Everything community-specific is stored in the database and configurable through the admin UI.
