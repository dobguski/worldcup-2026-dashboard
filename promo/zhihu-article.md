# 一个 HTML 文件跑完整个世界杯——我的 2026 实时看板开发回顾

一个月前西班牙在加时赛绝杀阿根廷夺冠的时候，我的看板正好跑完了第 105 场比赛。

Ferran Torres 106 分钟的进球落地的瞬间，dashboard 上的比分从 0-0 跳成 1-0，淘汰赛对阵图自动更新，射手榜上姆巴佩以 10 球锁定金靴——整个世界杯的数据链路，从 ESPN 的 API 到浏览器里那个 93KB 的 HTML 文件，在 30 秒内全部走完。

我想把这段经历写下来。不是为了炫耀——是真的踩了太多坑。

## 为什么是一个 HTML 文件

世界杯开赛前一周，我想做个看板。需求很简单：看比分、看积分榜、看出线形势。

常规做法：React/Vue + 图表库 + 后端 API + 数据库。但我当时想的是——世界杯就一个月，赛完就完了，值得搭一套全栈吗？

最后选了一条最极端的路：**一个 HTML 文件，零框架，零构建工具**。所有数据用静态 JSON 文件，Python 写个同步脚本定时从 ESPN/TSDB/FIFA 三个 API 拉数据更新。

93KB 的 `dashboard.html` 自己就是一个完整的单页应用——7 个标签页面（猜冠军、最新战报、淘汰赛、小组赛、射手榜、球队、简介），中英双语切换，比赛实时轮询，LocalStorage 投票，Polymarket 赔率 iframe 嵌入。没有 webpack，没有 npm install，GitHub Pages 直接部署。

> 仓库地址：https://github.com/dobguski/worldcup-2026-dashboard
> 在线看板：https://dobguski.github.io/worldcup-2026-dashboard/

## 技术架构：三个 API 一台戏

数据源有三个：

| 来源 | 说明 |
|------|------|
| ESPN API | 100 场实时比分，含点球 shootoutScore |
| TheSportsDB | 19 场详细赛果，免费 key=3 |
| FIFA API | 官方赛程 + 场地 + 观众人数 |

三个源各有利弊——ESPN 数据最全但不稳定（淘汰赛期间 SSL 直接崩了两天），TSDB 免费但只覆盖部分比赛，FIFA API 是官方数据但延迟高。

合并策略是 ESPN 优先。同场比赛三个源都返回结果时，ESPN > TSDB > FIFA。比分不同时出 correction 日志，人工确认后写入 `cup.txt`（Football.TXT 标准格式），再生成 `match_data.json`。

## 最难忘的 Bug

**Bug 1：淘汰赛数据被「吃掉了」**

R16 阶段某天醒来，发现前端淘汰赛标签页上阿根廷对佛得角的比赛凭空消失了，澳大利亚对埃及出现了两遍。

查了一圈发现问题出在 `update_match_in_file()`——这个函数负责把新比分写回 `cup.txt` 源文件。它用的是「内容搜索」定位目标行——在文件里找到包含相同队名和时间的行然后替换。

但淘汰赛阶段每天有 2-3 场比赛完赛，第一场更新后文件行号变了，第二场的搜索定位到了错误的行。结果就是 Australia-Egypt 的更新覆盖了 Argentina-Cape Verde，还产生了 42 条重复的 Netherlands-Morocco 行。

最后修了三个东西：
1. 从 git 历史恢复了干净的 `cup.txt`（手动删掉 40 条重复）
2. 把搜索逻辑回退为 `line_index`，但**所有更新按 line_index 降序排序**——从文件底部往上写，前面的行号不受影响
3. 加了 `.db_snapshots` 做数据备份，防止再次踩坑

**Bug 2：ESPN 的点球数据藏在哪**

加拿大对澳大利亚的 1/16 决赛打到点球大战，但 ESPN API 的 score 字段只显示 1-1。

翻了 ESPN 返回的原始 JSON 十分钟，才发现每个 competitor 对象里有一个 `shootoutScore` 字段——文档里根本没提。澳大利亚 `shootoutScore: 2`，埃及 `shootoutScore: 4`。

更坑的是，这个数据只在 `STATUS_FINAL_PEN` 状态下返回。如果在比赛还没结束的时候抓，它还是 null。

**Bug 3：GitHub Pages 的 CNAME 陷阱**

项目发布到 GitHub Pages 时，404 了两天。排查到最后发现是仓库里有个 `CNAME` 文件写了 `datamenu.xyz`——GitHub Pages 看到这个文件就尝试通过自定义域名提供服务，但 DNS 还指向旧的部署仓库，导致默认的 `github.io` URL 直接 404。

删掉 CNAME 文件，加了 `.nojekyll` 禁用 Jekyll 处理，再用 GitHub Actions 替代 legacy builder——终于通了。

## 数据开放

整个世界杯的数据现在以 CC0 协议公开——105 场比赛的结构化 JSON、181 名球员的 303 个进球、48 支球队的完整阵容、60 支球队的 621 条 Polymarket 赔率历史快照。

做数据分析的同学可以直接 load：

```python
import json, urllib.request
url = "https://dobguski.github.io/worldcup-2026-dashboard/match_data.json"
matches = json.loads(urllib.request.urlopen(url).read())
# 105 场比赛，字段含 home_team, away_team, home_score, away_score,
#          penalty_home, penalty_away, venue, date, is_result...
```

不需要下载任何东西，直接 HTTP GET 就能拿到。

## 经验总结

1. **单文件 HTML 没有想象中难维护**——93KB 对一个功能完善的看板来说完全够用，CSS 变量和内联 style 反而比分离的样式文件更方便定位和修改
2. **数据同步的边界情况比想象的复杂**——三个 API 源的数据合并、文件写回的行号偏移、点球数据的特殊状态、比赛进行中的 `(Live)` 标记 vs 完赛的 `(0-0)` 格式——这些细节占了开发时间的三分之二
3. **GitHub Pages 做生产部署有个坑**——legacy builder 已弃用但文档没说清楚，需要手动切换到 GitHub Actions
4. **公开数据是获得关注的最短路径**——与其讲技术细节，不如直接告诉别人「这里有 105 场比赛的完整数据，CC0 协议，随便用」

---

> 仓库：https://github.com/dobguski/worldcup-2026-dashboard
> 在线：https://dobguski.github.io/worldcup-2026-dashboard/
