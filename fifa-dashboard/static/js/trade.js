/**
 * FIFA 2026 仪表盘 — 交易面板
 * =============================
 * 用户可以直接在仪表盘中下单到 Polymarket CLOB API
 * 所有订单自动嵌入 dobguski Builder Code
 */
(function () {
    "use strict";

    let selectedTeamData = null;

    // ── 暴露到全局 ──────────────────────────────────────
    window.showTradePanel = function (teamName, prob, tokenId) {
        selectedTeamData = { team: teamName, prob: prob, tokenId: tokenId || "" };
        const panel = document.getElementById("trade-panel");

        if (!panel) return;

        // 更新面板标题
        document.getElementById("trade-team-name").textContent = teamName;
        document.getElementById("trade-team-prob").textContent = prob + "%";

        // 预填价格
        const priceInput = document.getElementById("trade-price");
        if (priceInput) priceInput.value = (prob / 100).toFixed(2);

        // 显示面板
        panel.style.display = "block";
        panel.scrollIntoView({ behavior: "smooth" });

        // 清除上次结果
        const resultDiv = document.getElementById("trade-result");
        if (resultDiv) resultDiv.innerHTML = "";
    };

    // ── 提交订单 ────────────────────────────────────────
    window.submitOrder = async function () {
        if (!selectedTeamData) return;

        const walletAddr = document.getElementById("trade-wallet").value.trim();
        const price = parseFloat(document.getElementById("trade-price").value);
        const size = parseFloat(document.getElementById("trade-size").value);
        const side = document.getElementById("trade-side").value;
        const tokenId = document.getElementById("trade-token-id").value.trim();
        const resultDiv = document.getElementById("trade-result");
        const submitBtn = document.getElementById("trade-submit-btn");

        // 校验
        if (!walletAddr) {
            resultDiv.innerHTML = '<div class="trade-error">请输入 Polymarket 钱包地址</div>';
            return;
        }
        if (!tokenId) {
            resultDiv.innerHTML = '<div class="trade-error">请输入市场 Token ID</div>';
            return;
        }
        if (isNaN(price) || price <= 0 || price > 1) {
            resultDiv.innerHTML = '<div class="trade-error">价格需在 0.01 - 1.00 之间</div>';
            return;
        }
        if (isNaN(size) || size <= 0) {
            resultDiv.innerHTML = '<div class="trade-error">数量需大于 0</div>';
            return;
        }

        // 发送请求
        submitBtn.disabled = true;
        submitBtn.textContent = "⏳ 下单中...";
        resultDiv.innerHTML = '<div class="trade-pending">⏳ 正在提交到 Polymarket CLOB...</div>';

        try {
            const resp = await fetch("/api/order", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    token_id: tokenId,
                    price: price,
                    size: size,
                    side: side,
                    wallet_address: walletAddr,
                }),
            });

            const data = await resp.json();

            if (data.success) {
                resultDiv.innerHTML = `
                    <div class="trade-success">
                        ✅ 订单已提交！<br>
                        <span class="text-dim">Builder: <strong>dobguski</strong></span><br>
                        <span class="text-dim">Order ID: ${data.data?.orderID || data.data?.id || "N/A"}</span>
                    </div>`;
            } else {
                const errMsg = data.error || JSON.stringify(data);
                resultDiv.innerHTML = `
                    <div class="trade-error">
                        ❌ 下单失败<br>
                        <span class="text-dim">${errMsg.substring(0, 200)}</span><br>
                        <span class="text-dim">提示：请确认钱包地址已充值 USDC 并有足够的交易授权</span>
                    </div>`;
            }
        } catch (err) {
            resultDiv.innerHTML = `<div class="trade-error">网络错误: ${err.message}</div>`;
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = "🚀 提交订单";
        }
    };

    // ── 绑定表格行点击 ──────────────────────────────────
    document.addEventListener("DOMContentLoaded", function () {
        const rows = document.querySelectorAll(".odds-table tbody tr");
        rows.forEach(row => {
            row.addEventListener("click", function () {
                const team = this.dataset.team;
                const prob = parseFloat(this.dataset.prob);
                const tokenId = this.dataset.tokenId || "";
                // 调用原有的趋势图更新 + 新的交易面板
                if (typeof updateTrendChart === "function") {
                    updateTrendChart(team);
                }
                window.showTradePanel(team, prob, tokenId);
            });
        });
    });
})();
