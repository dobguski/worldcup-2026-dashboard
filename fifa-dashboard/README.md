# ⚽ DobGuski FIFA 2026 仪表盘

> 中文 Polymarket 世界杯预测市场仪表盘 — 双版本

---

## 📦 版本说明

| | 静态版 | 动态版 |
|------|------|------|
| 文件 | `dashboard.html` | `app.py` + Flask |
| 部署 | 单文件拖放 | Railway / VPS |
| 后端 | 无 | Python Flask |
| 凭证暴露 | 零 | 环境变量 |
| CLOB 下单 | ❌ (链接跳转) | ✅ `/api/order` |
| 数据更新 | 手动替换 JSON | collector.py 自动 |
| 适用场景 | **datamenu.xyz 等静态托管** | 独立部署 + Builder 交易 |

---

## 🚀 静态版使用

```bash
# 1. 复制 dashboard.html 到你的服务器
scp dashboard.html user@host:/var/www/datamenu.xyz/

# 2. 更新数据：编辑 dashboard.html 中的 DATA 对象
#    搜索 `const DATA = {` 替换 teams/matches/analysis
```

零依赖、零服务器、零凭证。浏览器直接打开即可。

---

## 🔧 动态版使用

```bash
cd fifa-dashboard

# 1. 安装
pip install -r requirements.txt

# 2. 初始化数据
python collector.py --once

# 3. 启动
python app.py
# → http://localhost:5050

# 4. 生产部署 (Railway)
railway up
```

### 环境变量（生产环境必需）

| 变量 | 说明 |
|------|------|
| `BUILDER_NAME` | Builder 名称 (dobguski) |
| `BUILDER_CODE` | Builder Code (0xffcbd...) |
| `BUILDER_API_KEY` | API Key |
| `BUILDER_SECRET` | HMAC Secret (Base64) |
| `BUILDER_PASSPHRASE` | Passphrase |

本地开发：将凭证放在 `builder_config.json`（已 gitignore），自动回退读取。

### API 端点

| 端点 | 功能 |
|------|------|
| `GET /api/odds` | 冠军赔率 |
| `GET /api/matches` | 比赛列表 |
| `GET /api/analysis` | 分层分析 |
| `GET /api/history?team=法国` | 历史趋势 |
| `POST /api/order` | CLOB 下单（需凭证） |
| `GET /api/book?token_id=` | 订单簿查询 |

---

## 🔒 安全

- `builder_config.json` — gitignored，本地专用
- `docs/polymarket builder.txt` — gitignored，已删除
- 生产环境：凭证通过 Railway 环境变量注入
- 静态版：零凭证嵌入

---

## 📁 目录

```
fifa-dashboard/
├── dashboard.html          # ⭐ 静态版（单文件）
├── app.py                  # Flask 主应用
├── polymarket_api.py       # CLOB API HMAC 签名
├── collector.py            # 数据采集引擎
├── builder_config.json     # 本地凭证 (gitignored)
├── .env.example            # 环境变量模板
├── Procfile                # Railway 部署
├── runtime.txt             # Python 版本
├── requirements.txt
├── data/                   # 缓存数据
├── static/                 # CSS + JS
├── templates/              # Jinja2 模板
└── README.md
```
