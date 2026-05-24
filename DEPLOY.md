# Deploying MD Lotto Analyzer — AWS EC2

## Overview

| Piece | What it does | Cost |
|---|---|---|
| EC2 t2.micro | Runs the app 24/7 | Free tier (750 hrs/mo for 12 months, ~$8/mo after) |
| EBS 20 GB | Persistent disk for SQLite | Free tier (30 GB included) |
| Elastic IP | Fixed public IP | Free while attached to a running instance |

Access the app at `http://YOUR_ELASTIC_IP:8501`

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
   | Custom TCP | 8501 | 0.0.0.0/0 |
5. Click **Launch Instance**

---

## Step 2 — Assign an Elastic IP

1. In EC2 console → **Elastic IPs** → **Allocate Elastic IP address**
2. Click **Allocate**, then **Associate Elastic IP address**
3. Select your `md-lotto` instance → **Associate**
4. Note the IP address — this is your permanent app URL

---

## Step 3 — Set up the server

SSH into your instance:
```bash
ssh -i your-key.pem ubuntu@YOUR_ELASTIC_IP
```

Install Docker:
```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
newgrp docker   # apply group without logout

sudo apt-get install -y docker-compose-plugin
```

---

## Step 4 — Deploy the app

Clone the repo and start the container:
```bash
git clone https://github.com/m-ross-thornton/Lotto.git lotto
cd lotto
mkdir -p data
docker compose up -d --build
```

Verify it's running:
```bash
docker compose logs -f
# Should see scraper running and then "You can now view your Streamlit app in your browser"
```

Open `http://YOUR_ELASTIC_IP:8501` in a browser — the app should load.

---

## Adding to your Android home screen (PWA)

1. Open **Chrome** on your Android phone
2. Navigate to `http://YOUR_ELASTIC_IP:8501`
3. Tap **⋮ menu → Add to Home screen → Add**
4. An icon appears — opens the app fullscreen, no browser chrome

---

## Useful commands (from your Mac)

```bash
# SSH in
ssh -i your-key.pem ubuntu@YOUR_ELASTIC_IP

# View live app logs
ssh -i your-key.pem ubuntu@YOUR_ELASTIC_IP "cd lotto && docker compose logs -f"

# Restart app
ssh -i your-key.pem ubuntu@YOUR_ELASTIC_IP "cd lotto && docker compose restart"

# Pull latest code and redeploy
ssh -i your-key.pem ubuntu@YOUR_ELASTIC_IP "cd lotto && git pull && docker compose up -d --build"

# Manual scraper run
ssh -i your-key.pem ubuntu@YOUR_ELASTIC_IP "cd lotto && docker compose exec app python -m scraper.md_lottery"
```

---

## Updating the app

Push changes to GitHub, then on the server:
```bash
git pull && docker compose up -d --build
```
