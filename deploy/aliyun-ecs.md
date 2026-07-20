# Alibaba Cloud ECS Deployment · 阿里云轻应用服务器部署指南

以 Ubuntu 24.04 为例，从零部署世界小站到阿里云 ECS。

## Prerequisites · 前置条件

- 阿里云轻应用服务器（1核 1.6GB 内存即可）
- Ubuntu 24.04 LTS
- 已开放 80/443 端口（安全组规则）
- SSH 登录权限

## Step 1: Server Setup · 服务器初始化

```bash
ssh root@你的服务器IP

# Update system
apt update && apt upgrade -y

# Install nginx + python3
apt install -y nginx python3
```

## Step 2: Clone Repository · 克隆仓库

```bash
cd /opt
git clone https://github.com/dobguski/worldcup-2026-dashboard.git worldcup-live
```

## Step 3: Configure Nginx · 配置 Nginx

```bash
# Copy example config
cp /opt/worldcup-live/deploy/nginx-example.conf /etc/nginx/sites-available/worldcup

# Edit domain name
nano /etc/nginx/sites-available/worldcup
# Change "datamenu.xyz" to your domain

# Enable site
ln -s /etc/nginx/sites-available/worldcup /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

## Step 4: Start Sync Server · 启动同步服务

```bash
# Copy systemd unit
cp /opt/worldcup-live/deploy/systemd-example.service /etc/systemd/system/worldcup-sync.service

# Edit paths if needed
nano /etc/systemd/system/worldcup-sync.service

# Enable and start
systemctl daemon-reload
systemctl enable worldcup-sync
systemctl start worldcup-sync
```

## Step 5: Verify · 验证

```bash
# Check services
systemctl status nginx
systemctl status worldcup-sync

# Test HTTP
curl http://localhost/ -o /dev/null -w "%{http_code}"
# Should return: 200

# Check data files
curl http://localhost/match_data.json | python3 -m json.tool | head
```

## Optional: SSL with Let's Encrypt

```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d your-domain.com
```

## Troubleshooting · 故障排查

```bash
# Check nginx error log
tail -f /var/log/nginx/error.log

# Check sync server log
journalctl -u worldcup-sync -f

# Check if port 80 is listening
ss -tlnp | grep 80
```
