# Deploying MD Lotto Analyzer — AWS EC2

## Overview

| Piece | What it does | Cost |
|---|---|---|
| EC2 t2.micro | Runs the app 24/7 | Free tier (750 hrs/mo for 12 months, ~$8/mo after) |
| EBS 20 GB | Persistent disk for SQLite | Free tier (30 GB included) |
| Elastic IP | Fixed public IP | Free while attached to a running instance |
| DuckDNS | Free subdomain (e.g. `md-lotto.duckdns.org`) | Free |
| Let's Encrypt | HTTPS certificate | Free |
| Nginx | Reverse proxy + SSL termination | Free |

---

## Step 1 — Launch an EC2 instance

1. Open the [EC2 console](https://console.aws.amazon.com/ec2/)
2. Click **Launch Instance**
3. Configure:
   - **Name:** `md-lotto`
   - **AMI:** Ubuntu Server 22.04 LTS (free tier eligible)
   - **Instance type:** `t2.micro` (free tier eligible)
   - **Key pair:** create or select one — you'll need the `.pem` file to SSH in
   - **Storage:** 20 GB gp3 (free tier includes 30 GB)
4. Under **Network settings → Security group**, add inbound rules:
   | Type | Port | Source |
   |---|---|---|
   | SSH | 22 | My IP |
   | HTTP | 80 | 0.0.0.0/0 |
   | HTTPS | 443 | 0.0.0.0/0 |
5. Click **Launch Instance**

---

## Step 2 — Assign an Elastic IP

1. In EC2 console → **Elastic IPs** → **Allocate Elastic IP address**
2. Click **Allocate**, then **Associate Elastic IP address**
3. Select your `md-lotto` instance → **Associate**
4. Note the IP address — you'll use it in Step 3

---

## Step 3 — Get a free DuckDNS domain

1. Go to [duckdns.org](https://www.duckdns.org) and sign in (GitHub/Google)
2. Pick a subdomain, e.g. `md-lotto` → click **Add Domain**
3. Set the IP to your Elastic IP → **Update IP**
4. Copy your **token** from the top of the page

---

## Step 4 — Set up the server

SSH into your instance:
```bash
ssh -i your-key.pem ubuntu@YOUR_ELASTIC_IP
```

Install Docker, Nginx, and Certbot:
```bash
# Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
newgrp docker   # apply group without logout

# Docker Compose plugin
sudo apt-get install -y docker-compose-plugin

# Nginx + Certbot
sudo apt-get install -y nginx certbot python3-certbot-nginx
```

---

## Step 5 — Deploy the app

Clone the repo and start the container:
```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git lotto
cd lotto
mkdir -p data
docker compose up -d --build
```

Verify it's running:
```bash
docker compose logs -f
# Should see scraper running and then "You can now view your Streamlit app in your browser"
```

Test locally on the server:
```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8501
# Should return 200
```

---

## Step 6 — Set up Nginx + HTTPS

Copy and edit the Nginx config:
```bash
sudo cp ~/lotto/deploy/nginx.conf /etc/nginx/sites-available/mdlotto

# Replace YOUR_DOMAIN with your actual subdomain (e.g. md-lotto)
sudo sed -i 's/YOUR_DOMAIN/md-lotto/g' /etc/nginx/sites-available/mdlotto

sudo ln -s /etc/nginx/sites-available/mdlotto /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

Get the SSL certificate (replace with your domain):
```bash
sudo certbot --nginx -d md-lotto.duckdns.org
```
Follow the prompts — Certbot auto-configures Nginx for HTTPS.

Test HTTPS:
```bash
curl -s -o /dev/null -w "%{http_code}" https://md-lotto.duckdns.org
# Should return 200
```

---

## Step 7 — Keep DuckDNS updated (optional)

Elastic IPs are fixed, so this is only needed if you ever stop/restart the instance
and AWS reassigns the IP (it won't if Elastic IP stays associated).

```bash
# Edit the script with your domain and token
nano ~/lotto/deploy/duckdns-renew.sh
chmod +x ~/lotto/deploy/duckdns-renew.sh

# Add to crontab
(crontab -l 2>/dev/null; echo "*/5 * * * * /home/ubuntu/lotto/deploy/duckdns-renew.sh >> /var/log/duckdns.log 2>&1") | crontab -
```

---

## Adding to your Android home screen (PWA)

1. Open **Chrome** on your Android phone
2. Navigate to `https://md-lotto.duckdns.org`
3. Tap **⋮ menu → Add to Home screen → Add**
4. An icon appears — opens the app fullscreen, no browser chrome

---

## Useful commands (from your Mac)

```bash
# SSH in
ssh -i your-key.pem ubuntu@YOUR_ELASTIC_IP

# View live app logs
ssh ... "cd lotto && docker compose logs -f"

# Restart app
ssh ... "cd lotto && docker compose restart"

# Pull latest code and redeploy
ssh ... "cd lotto && git pull && docker compose up -d --build"

# Manual scraper run
ssh ... "cd lotto && docker compose exec app python -m scraper.md_lottery"
```

---

## Updating the app

```bash
# On your Mac — push changes to git, then on the server:
git pull && docker compose up -d --build
```

Or set up a GitHub Action to auto-deploy on push to `main`.
