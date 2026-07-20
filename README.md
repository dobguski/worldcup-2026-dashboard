# ⚽ 2026 FIFA World Cup Live Dashboard · 2026世界杯实时数据看板

> **48 Teams · 105 Matches · Live Scores · Standings · Polymarket Predictions**
> **48支球队 · 105场比赛 · 实时比分 · 积分榜 · 预测市场赔率**

A pure HTML/CSS/JS dashboard tracking the entire 2026 FIFA World Cup tournament — from group stage to the final at MetLife Stadium. Zero framework dependencies. Runs on GitHub Pages, any static server, or nginx + Python sync engine.

纯前端 HTML/CSS/JS 构建的世界杯实时看板，零框架依赖。支持 GitHub Pages 一键部署，也可搭配 Python 同步引擎实现实时数据更新。完整记录 2026 年世界杯全部 105 场比赛。

---

## 🏆 Champion · 冠军

<p align="center">
  <b>🇪🇸 Spain · 西班牙</b><br>
  Spain 1–0 Argentina (AET)<br>
  <i>Ferran Torres 106' | MetLife Stadium | 80,663</i>
</p>

---

## 📸 Dashboard · 看板预览

| 标签 Tab | 内容 Content |
|----------|-------------|
| 🏆 淘汰赛 | 完整淘汰赛对阵 + 比分 + 晋级路线 |
| ⚽ 射手榜 | 181 名球员 · 303 进球（前20一览，展开全部） |
| 📊 积分榜 | 12 组 × 4 队 小组积分 |
| ⚡ 最新战报 | 按日期分组，105 场比赛卡片 |
| 📈 猜冠军 | Polymarket 实时冠军赔率（60 队） |

---

## ✨ Features · 功能亮点

| 模块 | 说明 |
|------|------|
| 🏆 淘汰赛对阵 | R32 → R16 → QF → SF → Final 全路径，胜者加粗 + 箭头，点球 PK 标注 |
| ⚽ 射手榜 | 181 人 / 303 球，前 20 名一屏展示，20+ 点击展开，金靴 Mbappé 10 球 |
| 📊 积分榜 | 12 个小组自动排序，最佳第三名 ✓ 晋级标注 |
| ⚡ 最新战报 | 按日期分组卡片，实时比分 + 半场比分 + 点球数据 |
| 📈 猜冠军 | iframe 嵌入 Railway Flask 应用，Polymarket CLOB 实时赔率 |
| 🌐 中英双语 | 一键切换中文 / English / 双语 |
| 📱 响应式 | 手机 / 平板 / 桌面全适配 |
| 🔄 自动刷新 | 进行中比赛 15s 轮询，完赛后 30s 轮询 |

---

## 👥 Who is this for · 适用人群

| 如果你... | 你可以... |
|-----------|----------|
| 🎓 在学前端 | 研究纯 HTML/CSS/JS (93KB 单文件) 如何构建完整应用——双语切换、实时轮询、响应式布局、LocalStorage 投票 |
| 📊 做数据分析 | 直接下载结构化 JSON 数据做世界杯统计分析——105 场比赛、181 名射手、303 个进球 |
| ⚽ 是球迷 | 回顾 2026 世界杯全部比赛——从小组赛到决赛，含比分、点球、半场数据 |
| 💰 研究预测市场 | 学习 Polymarket CLOB API 集成：60 队赔率采集、621 条历史快照、HMAC 签名认证 |
| 🔧 想二次开发 | Fork 后替换数据源，适配其他赛事（欧洲杯、亚洲杯、联赛均可） |
| 🚀 学部署运维 | 参考 GitHub Pages / Nginx / systemd / Railway / Alibaba Cloud 五种部署方案 |

---

## 🛠 How to use · 可以这样使用

### 📊 数据分析（无需下载，直接用）

```python
import json, urllib.request

# 直接从 GitHub Pages 加载数据
url = "https://dobguski.github.io/worldcup-2026-dashboard/match_data.json"
matches = json.loads(urllib.request.urlopen(url).read())

# 统计各队进球
goals = {}
for m in matches:
    for team in [m['home_team'], m['away_team']]:
        goals[team] = goals.get(team, 0) + (m.get('home_score') or 0) if team == m['home_team'] else (m.get('away_score') or 0)

# 导出 CSV
import csv
with open('worldcup2026.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=matches[0].keys())
    w.writeheader(); w.writerows(matches)
```

### 🎨 二次开发（Fork 后改数据源）

```bash
git clone https://github.com/dobguski/worldcup-2026-dashboard.git
cd worldcup-2026-dashboard
python3 -m http.server 8080    # 本地预览
# 修改 dashboard.html 的数据 URL，换成你的 JSON
# 或替换 match_data.json 为其他赛事数据
```

### ⚽ 适配其他赛事

数据结构是标准的——只需替换 JSON 文件即可适配欧洲杯、亚洲杯、联赛等：

```json
{
  "home_team": "Spain",
  "away_team": "Argentina",
  "home_score": 1, "away_score": 0,
  "group": "KO",
  "date": "2026-07-20",
  "venue": "MetLife Stadium",
  "penalty_home": null, "penalty_away": null
}
```

替换 `match_data.json`、`standings.json`、`team_names.json` 三个文件，看板自动适配新赛事。

### 🔗 嵌入你的网站

```html
<!-- 直接 iframe 嵌入完整看板 -->
<iframe src="https://dobguski.github.io/worldcup-2026-dashboard/dashboard.html"
        style="width:100%;height:100vh;border:none"></iframe>
```

---

## 🚀 Quick Start · 快速开始

### Option 1: GitHub Pages (simplest · 最简单)

1. Fork 本仓库
2. Settings → Pages → Source: `main` branch, root directory
3. 等待 1 分钟后访问 `https://你的用户名.github.io/worldcup-2026-dashboard/`

无需任何构建步骤，静态文件直接运行。

### Option 2: Local HTTP Server · 本地运行

```bash
# Python 3
cd worldcup-2026-dashboard
python3 -m http.server 8080
# 打开 http://localhost:8080/dashboard.html
```

### Option 3: Full Sync Engine · 完整同步引擎

```bash
cd worldcup-2026-dashboard
python3 sync_worldcup.py         # 单次数据同步
python3 sync_worldcup.py --serve # 启动 Web 服务器 + 自动同步
```

---

## 📊 Data Sources · 数据源

| 来源 | 类型 | 说明 |
|------|------|------|
| [ESPN API](https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard) | 实时比分 | 100 场比赛，含点球数据 |
| [TheSportsDB](https://www.thesportsdb.com/api/v1/json/3/) | 详细赛果 | 免费 key=3，19 场数据 |
| [FIFA API](https://api.fifa.com/api/v3/calendar/matches) | 官方赛程 | 含场地、观众人数等 |
| [Polymarket](https://polymarket.com/) | 预测赔率 | Gamma API + CLOB midpoint |
| [openfootball/worldcup](https://github.com/openfootball/worldcup) | Football.TXT | 赛程格式标准 |

---

## 🛠 Tech Stack · 技术栈

| 层 | 技术 |
|----|------|
| **Frontend** | Pure HTML/CSS/JS (零框架) |
| **Backend** | Python 3 (标准库 `http.server` + `urllib`) |
| **Sync Engine** | 多源数据融合 (ESPN + TSDB + FIFA) |
| **Deploy** | GitHub Pages / Nginx / Caddy / Alibaba Cloud ECS |
| **PM App** | Flask + gunicorn + Polymarket CLOB API |
| **Data Format** | JSON (所有比赛数据) + Football.TXT (赛程源) |

---

## 📂 Project Structure · 项目结构

```
worldcup-2026-dashboard/
├── dashboard.html           ← 主看板 (93KB, 零依赖)
├── welcome.html             ← 欢迎页
├── index.html               ← 入口
│
├── sync_worldcup.py         ← 多源数据同步引擎
├── run_server.py            ← 自动重启 + 服务器启动器
│
├── match_data.json          ← 105 场比赛数据
├── goalscorers.json         ← 181 人 / 303 球
├── bracket_data.json        ← 淘汰赛对阵结构
├── standings.json           ← 12 组积分榜
├── teams.json               ← 48 队详细数据
├── team_names.json          ← 中英文队名对照
├── polymarket.json          ← 预测市场赔率
├── player_details.json      ← 球员详情
├── wiki_squads.json         ← 阵容数据
│
├── 2026--usa/               ← Football.TXT 赛程源文件
│   ├── cup.txt              ← 全部 105 场比赛（含进球详情）
│   └── cup_finals.txt       ← 决赛特殊赛程
│
├── scripts/                 ← 工具脚本
│   ├── auto_pipeline.py     ← 全流程自动化
│   ├── fetch_matches.py     ← 赛程抓取
│   ├── fetch_goal_scorers.py← 射手榜更新
│   ├── auto_qa.py           ← 自动质量检查
│   └── health_check.py      ← 健康监控
│
├── fifa-dashboard/          ← Polymarket 赔率 Flask 应用
│   ├── app.py               ← Flask API + 路由
│   ├── collector.py         ← 数据采集引擎
│   ├── templates/           ← Jinja2 模板
│   └── static/              ← CSS + JS
│
└── deploy/                  ← 部署配置
    ├── nginx-example.conf   ← Nginx 反向代理模板
    ├── systemd-example.service ← systemd 后台服务
    ├── github-pages.md      ← GitHub Pages 部署指南
    └── aliyun-ecs.md        ← 阿里云部署指南
```

---

## 📈 Data Files · 数据文件

| 文件 | 大小 | 说明 |
|------|------|------|
| `match_data.json` | 55 KB | 105 场比赛：主客队、比分、半场、点球、场地、时间（UTC+8） |
| `goalscorers.json` | 24 KB | 181 名射手：球员名（中/英）、进球数、按进球降序 |
| `bracket_data.json` | 5.5 KB | 淘汰赛对阵：R32 → R16 → QF → SF → Final + 冠军 |
| `standings.json` | 8 KB | 12 组积分：场次、胜平负、进球/失球、净胜球、积分 |
| `teams.json` | 524 KB | 48 队：队名、国旗、FIFA 排名、历史战绩 |
| `team_names.json` | 1.3 KB | 中英文队名对照（48 队） |
| `polymarket.json` | 25 KB | 冠军赔率：60 队概率 + 交易量 |
| `player_details.json` | 827 KB | 球员详情：位置、年龄、俱乐部、国家队出场 |
| `wiki_squads.json` | 399 KB | 48 队完整阵容名单 |
| `visitors.json` | 12 KB | 访客日志（时区、语言、时间戳） |
| `counter.json` | 0.2 KB | 访客计数器 |

---

## 🌐 Deployment · 部署指南

### GitHub Pages (免费)

参见 [deploy/github-pages.md](deploy/github-pages.md)

### Alibaba Cloud ECS (生产环境)

参见 [deploy/aliyun-ecs.md](deploy/aliyun-ecs.md)

### Railway (Flask 应用)

```bash
cd fifa-dashboard
railway up --service dobguski-fifa2026
```

---

## 🔒 Security · 安全

- 本仓库**不含任何 API 密钥或凭证**
- `builder_config.json`（Polymarket 密钥）已通过 `.gitignore` 排除
- 生产环境请使用环境变量注入敏感配置
- 推荐使用 GitHub Secrets 管理部署密钥

---

## 🔗 Links · 链接

- **Live Site**: [datamenu.xyz](https://datamenu.xyz)
- **PM Predictions**: [dobguski-fifa2026-production.up.railway.app](https://dobguski-fifa2026-production.up.railway.app)
- **Data Format**: [openfootball/worldcup](https://github.com/openfootball/worldcup)
- **FIFA Official**: [fifa.com](https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026)

---

## 📄 License · 许可证

[CC0 1.0 Universal](LICENSE) — Public Domain Dedication · 公共领域贡献

任何人可以自由复制、修改、分发本作品，甚至用于商业目的，无需征求许可。

---

Built with ❤️ by [DobGuski](https://github.com/dobguski) during the 2026 FIFA World Cup.
