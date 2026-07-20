# GitHub Pages Deployment Guide · 部署指南

## Step 1: Fork the Repository

Click the **Fork** button at the top-right of [this repository](https://github.com/dobguski/worldcup-2026-dashboard).

## Step 2: Enable GitHub Pages

1. Go to your forked repo → **Settings** → **Pages**
2. Under "Build and deployment":
   - **Source**: Deploy from a branch
   - **Branch**: `main` → `/ (root)` → Save
3. Wait 1–2 minutes. GitHub will show: "Your site is live at https://你的用户名.github.io/worldcup-2026-dashboard/"

## Step 3: (Optional) Custom Domain

1. In Settings → Pages → Custom domain, enter your domain (e.g., `datamenu.xyz`)
2. At your DNS provider, add:
   - **CNAME** record: `datamenu.xyz` → `你的用户名.github.io`
   - OR **A records** pointing to GitHub Pages IPs (see [GitHub docs](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site))
3. Check "Enforce HTTPS"

## Updating

Just push new commits to the `main` branch. GitHub Pages automatically redeploys within 1–2 minutes.

```bash
git add .
git commit -m "Update match data"
git push origin main
```

## Files Served

All static files in the repository root are served directly:
- `dashboard.html` → `https://你的域名/dashboard.html`
- `match_data.json` → `https://你的域名/match_data.json`
- etc.
