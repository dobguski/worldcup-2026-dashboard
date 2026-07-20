/**
 * FIFA 2026 仪表盘 — 前端交互逻辑
 * ====================================
 * 功能：自动刷新、状态指示器、表格交互、无外部依赖
 */
(function () {
    "use strict";

    // ── 状态管理 ────────────────────────────────────────
    const REFRESH_INTERVAL = 30000; // 30秒轮询
    const STALE_THRESHOLD = 3600000; // 1小时未更新 = 过期

    let refreshTimer = null;
    let selectedTeam = null;

    // ── 状态指示器 ──────────────────────────────────────
    function updateStatus() {
        fetch("/api/status")
            .then(r => r.json())
            .then(data => {
                const dot = document.getElementById("status-dot");
                const text = document.getElementById("status-text");
                if (!dot || !text) return;

                text.textContent = data.data_available
                    ? `数据更新: ${data.last_updated}`
                    : "暂无数据";

                if (!data.data_available) {
                    dot.className = "status-dot stale";
                } else {
                    // 检查数据是否过期
                    const updated = new Date(data.last_updated);
                    const age = Date.now() - updated.getTime();
                    dot.className = age > STALE_THRESHOLD ? "status-dot stale" : "status-dot live";
                }
            })
            .catch(() => {
                const dot = document.getElementById("status-dot");
                const text = document.getElementById("status-text");
                if (dot) dot.className = "status-dot stale";
                if (text) text.textContent = "连接失败";
            });
    }

    // ── 表格行点击交互（冠军赔率页） ────────────────────
    function initTableInteraction() {
        const rows = document.querySelectorAll(".odds-table tbody tr");
        rows.forEach(row => {
            row.addEventListener("click", function () {
                // 切换选中状态
                rows.forEach(r => r.classList.remove("selected"));
                this.classList.add("selected");

                // 更新趋势图
                const team = this.dataset.team;
                if (team && typeof updateTrendChart === "function") {
                    selectedTeam = team;
                    updateTrendChart(team);
                }
            });
        });

        // 默认选中第一行
        if (rows.length > 0) {
            rows[0].classList.add("selected");
            const firstTeam = rows[0].dataset.team;
            if (firstTeam && typeof updateTrendChart === "function") {
                selectedTeam = firstTeam;
                updateTrendChart(firstTeam);
            }
        }
    }

    // ── 比赛过滤标签 ────────────────────────────────────
    function initMatchTabs() {
        const tabs = document.querySelectorAll(".tab");
        const cards = document.querySelectorAll(".match-card");

        tabs.forEach(tab => {
            tab.addEventListener("click", function () {
                tabs.forEach(t => t.classList.remove("active"));
                this.classList.add("active");

                const filter = this.dataset.filter;
                cards.forEach(card => {
                    if (filter === "all") {
                        card.style.display = "";
                    } else if (filter === "upsets") {
                        card.style.display = card.classList.contains("upset") ? "" : "none";
                    } else if (filter === "correct") {
                        card.style.display = card.classList.contains("favorite-won") ? "" : "none";
                    }
                });
            });
        });
    }

    // ── 手动刷新按钮 ────────────────────────────────────
    function initRefreshButton() {
        const btn = document.getElementById("btn-refresh");
        if (btn) {
            btn.addEventListener("click", function () {
                this.textContent = "⏳ 刷新中...";
                this.disabled = true;
                location.reload();
            });
        }
    }

    // ── 自动刷新（轮询状态 + 数据更新） ─────────────────
    function startAutoRefresh() {
        updateStatus();
        refreshTimer = setInterval(updateStatus, REFRESH_INTERVAL);
    }

    // ── 响应式处理 ──────────────────────────────────────
    function handleResponsive() {
        const navLinks = document.querySelector(".nav-links");
        if (window.innerWidth < 600 && navLinks) {
            navLinks.style.gap = "0px";
        }
    }

    // ── 初始化 ──────────────────────────────────────────
    document.addEventListener("DOMContentLoaded", function () {
        startAutoRefresh();
        initTableInteraction();
        initMatchTabs();
        initRefreshButton();
        handleResponsive();
    });

    window.addEventListener("resize", handleResponsive);

    // 页面卸载时清理定时器
    window.addEventListener("beforeunload", function () {
        if (refreshTimer) clearInterval(refreshTimer);
    });
})();
