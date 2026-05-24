# Deploying to Fly.io

## One-time setup

### 1. Install flyctl
```bash
brew install flyctl
fly auth login
```

### 2. Create the app and volume
```bash
# Create the app (uses fly.toml config, skips deploy for now)
fly launch --no-deploy

# Create a 1 GB persistent volume for SQLite in the same region
fly volumes create lotto_data --region iad --size 1
```

### 3. Deploy
```bash
fly deploy
```

The app will be live at `https://md-lotto-analyzer.fly.dev`.

---

## What happens on deploy

- Docker image is built and pushed
- Streamlit starts on port 8501
- `entrypoint.sh` runs the scraper immediately on boot, then every 24 hours automatically
- SQLite database is stored on the persistent volume at `/app/data/lotto.db` — survives redeploys

---

## Subsequent deploys
```bash
fly deploy
```

---

## Useful commands
```bash
fly logs                  # tail live logs
fly ssh console           # shell into the running machine
fly volumes list          # check volume status
fly status                # machine health
```

---

## Adding to your Android home screen (PWA)

1. Open Chrome on your Android phone
2. Navigate to `https://md-lotto-analyzer.fly.dev`
3. Tap the **⋮ menu → Add to Home screen**
4. Tap **Add** — an icon appears on your home screen
5. Opening it launches the app fullscreen with no browser chrome

> The manifest, icons, and theme colour are already configured in the app.

---

## Updating the app name

If `md-lotto-analyzer` is already taken on Fly.io, edit `fly.toml`:
```toml
app = "your-unique-app-name"
```
Then re-run `fly launch --no-deploy` to register the new name.
