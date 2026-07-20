/**
 * FIFA 2026 仪表盘 — Chart.js 图表配置
 * ======================================
 * 依赖: Chart.js 4.x (CDN)
 */

// ── 配色方案 ────────────────────────────────────────────
const COLORS = {
    blue: "#3b82f6",
    green: "#22c55e",
    red: "#ef4444",
    orange: "#f97316",
    yellow: "#f59e0b",
    purple: "#a855f7",
    teal: "#14b8a6",
    pink: "#ec4899",
    surface: "#1a1d27",
    border: "#2a2d3a",
    text: "#e1e4ed",
    textDim: "#8b8fa3",
    gridLine: "rgba(42,45,58,0.5)",
};

Chart.defaults.color = COLORS.textDim;
Chart.defaults.borderColor = COLORS.border;
Chart.defaults.font.family = "-apple-system, BlinkMacSystemFont, 'Microsoft YaHei', 'PingFang SC', sans-serif";

// ── 通用插件：深色主题背景 ──────────────────────────────
const darkBgPlugin = {
    id: "darkBg",
    beforeDraw(chart) {
        const ctx = chart.ctx;
        ctx.save();
        ctx.fillStyle = COLORS.surface;
        ctx.fillRect(0, 0, chart.width, chart.height);
        ctx.restore();
    },
};

// ============================================================
// 图表 1: 冠军赔率横向柱状图
// ============================================================
function createOddsBarChart(canvasId, teams) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || !teams || teams.length === 0) return null;

    // 取 Top 10，反转以便从上到下
    const top10 = teams.slice(0, 10).reverse();

    const labels = top10.map(t => `${t.flag || ""} ${t.team}`);
    const data = top10.map(t => t.prob);
    const barColors = top10.map(t => {
        if (t.trend === "up") return COLORS.green;
        if (t.trend === "down") return COLORS.red;
        return COLORS.blue;
    });

    // 销毁旧图表
    const existing = Chart.getChart(canvas);
    if (existing) existing.destroy();

    return new Chart(canvas, {
        type: "bar",
        data: {
            labels: labels,
            datasets: [{
                label: "冠军概率 (%)",
                data: data,
                backgroundColor: barColors.map(c => c + "33"),
                borderColor: barColors,
                borderWidth: 1.5,
                borderRadius: 4,
                borderSkipped: false,
            }],
        },
        options: {
            indexAxis: "y",
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: ctx => ` ${ctx.raw}% 冠军概率`,
                    },
                },
            },
            scales: {
                x: {
                    title: { display: true, text: "概率 (%)" },
                    max: Math.max(...data) * 1.2,
                    grid: { color: COLORS.gridLine },
                },
                y: {
                    grid: { display: false },
                    ticks: { font: { size: 13 } },
                },
            },
        },
        plugins: [darkBgPlugin],
    });
}

// ============================================================
// 图表 2: 历史趋势折线图
// ============================================================
async function updateTrendChart(team) {
    const canvas = document.getElementById("trendChart");
    if (!canvas) return;

    try {
        const resp = await fetch(`/api/history?team=${encodeURIComponent(team)}`);
        const data = await resp.json();

        const labels = data.trend.map(p => {
            const d = new Date(p.timestamp);
            return `${d.getMonth() + 1}/${d.getDate()}`;
        });
        const values = data.trend.map(p => p.prob);

        const existing = Chart.getChart(canvas);
        if (existing) existing.destroy();

        new Chart(canvas, {
            type: "line",
            data: {
                labels: labels,
                datasets: [{
                    label: `${team} 冠军概率 (%)`,
                    data: values,
                    borderColor: COLORS.blue,
                    backgroundColor: COLORS.blue + "22",
                    borderWidth: 2,
                    pointBackgroundColor: COLORS.blue,
                    pointRadius: 5,
                    pointHoverRadius: 8,
                    fill: true,
                    tension: 0.3,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: true, labels: { color: COLORS.text, font: { size: 13 } } },
                },
                scales: {
                    x: {
                        grid: { color: COLORS.gridLine },
                        title: { display: true, text: "日期" },
                    },
                    y: {
                        grid: { color: COLORS.gridLine },
                        title: { display: true, text: "概率 (%)" },
                        beginAtZero: false,
                    },
                },
            },
            plugins: [darkBgPlugin],
        });

        // 更新标题
        const title = document.getElementById("trend-title");
        if (title) title.textContent = `📉 ${team} 概率趋势`;

        // 更新数据点数
        const count = document.getElementById("trend-count");
        if (count) count.textContent = `${data.data_points} 个数据点`;

    } catch (err) {
        console.error("趋势数据加载失败:", err);
    }
}

// ============================================================
// 图表 3: 分层胜率柱状图
// ============================================================
function createTierChart(canvasId, tiers) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || !tiers || tiers.length === 0) return null;

    const labels = tiers.map(t => t.label);
    const winRates = tiers.map(t => t.rate);
    const barColors = tiers.map(t => {
        switch (t.color) {
            case "super": return COLORS.red;
            case "strong": return COLORS.blue;
            case "mild": return COLORS.yellow;
            case "weak": return COLORS.orange;
            default: return COLORS.purple;
        }
    });

    const existing = Chart.getChart(canvas);
    if (existing) existing.destroy();

    return new Chart(canvas, {
        type: "bar",
        data: {
            labels: labels,
            datasets: [
                {
                    label: "热门获胜率 (%)",
                    data: winRates,
                    backgroundColor: barColors.map(c => c + "44"),
                    borderColor: barColors,
                    borderWidth: 1.5,
                    borderRadius: 6,
                    borderSkipped: false,
                },
                {
                    type: "line",
                    label: "抛硬币基线 (50%)",
                    data: Array(labels.length).fill(50),
                    borderColor: COLORS.textDim,
                    borderWidth: 1.5,
                    borderDash: [6, 4],
                    pointRadius: 0,
                    fill: false,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    labels: { color: COLORS.text, usePointStyle: true },
                },
                tooltip: {
                    callbacks: {
                        label: function (ctx) {
                            if (ctx.datasetIndex === 0) {
                                const tier = tiers[ctx.dataIndex];
                                return [`胜率: ${tier.rate}%`, `${tier.wins}/${tier.count} 场`, tier.examples];
                            }
                            return "50% 随机基线";
                        },
                    },
                },
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { font: { size: 11 } },
                },
                y: {
                    max: 110,
                    grid: { color: COLORS.gridLine },
                    title: { display: true, text: "胜率 (%)" },
                    ticks: {
                        callback: v => v + "%",
                    },
                },
            },
        },
        plugins: [darkBgPlugin],
    });
}

// ============================================================
// 图表 4: 概率分布气泡图（首页概览）
// ============================================================
function createDistributionChart(canvasId, teams) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || !teams || teams.length === 0) return null;

    const data = teams.map(t => ({
        x: t.rank,
        y: t.prob,
        r: Math.max(t.prob * 0.4, 4),
        label: t.team,
        trend: t.trend,
    }));

    const existing = Chart.getChart(canvas);
    if (existing) existing.destroy();

    return new Chart(canvas, {
        type: "bubble",
        data: {
            datasets: [{
                label: "球队",
                data: data,
                backgroundColor: data.map(d => {
                    if (d.trend === "up") return COLORS.green + "88";
                    if (d.trend === "down") return COLORS.red + "88";
                    return COLORS.blue + "88";
                }),
                borderColor: data.map(d => {
                    if (d.trend === "up") return COLORS.green;
                    if (d.trend === "down") return COLORS.red;
                    return COLORS.blue;
                }),
                borderWidth: 1.5,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: ctx => {
                            const d = ctx.raw;
                            return `${d.label}: ${d.y}% (排名 #${d.x})`;
                        },
                    },
                },
            },
            scales: {
                x: {
                    title: { display: true, text: "排名" },
                    grid: { color: COLORS.gridLine },
                    reverse: true,
                    ticks: { stepSize: 1 },
                },
                y: {
                    title: { display: true, text: "概率 (%)" },
                    grid: { color: COLORS.gridLine },
                },
            },
        },
        plugins: [darkBgPlugin],
    });
}
