/**
 * 钱包连接管理
 * ================
 * MetaMask 登录 → Safe 部署 → 代币授权 → 下单
 */
(function () {
    "use strict";

    let currentAccount = null;
    let safeAddress = null;
    let magicInstance = null;

    // ── Magic Link 初始化（可选，需 API Key） ──────────────
    const MAGIC_API_KEY = window.MAGIC_PUBLISHABLE_KEY || "";

    function initMagic() {
        if (!MAGIC_API_KEY || typeof Magic === "undefined") return null;
        if (magicInstance) return magicInstance;
        try {
            magicInstance = new Magic(MAGIC_API_KEY, {
                network: { rpcUrl: "https://polygon-rpc.com", chainId: 137 },
            });
        } catch (e) {
            console.warn("Magic init failed:", e);
        }
        return magicInstance;
    }

    // ── 连接钱包（MetaMask 优先，Magic Link 备选）──────────
    window.connectWallet = async function () {
        const btn = document.getElementById("wallet-btn");

        // 尝试 MetaMask
        if (typeof window.ethereum !== "undefined") {
            try {
                const accounts = await window.ethereum.request({ method: "eth_requestAccounts" });
                currentAccount = accounts[0];
                updateWalletUI();
                await checkSafeStatus();
                return;
            } catch (e) {
                console.warn("MetaMask rejected:", e.message);
            }
        }

        // 尝试 Magic Link
        const magic = initMagic();
        if (magic) {
            try {
                const accounts = await magic.wallet.connectWithUI();
                currentAccount = accounts[0];
                updateWalletUI();
                await checkSafeStatus();
                return;
            } catch (e) {
                console.warn("Magic Link failed:", e);
            }
        }

        // 兜底：手动输入地址
        const addr = prompt("请输入你的 Polygon 钱包地址 (0x...)：");
        if (addr && addr.startsWith("0x") && addr.length === 42) {
            currentAccount = addr;
            updateWalletUI();
            await checkSafeStatus();
        }
    };

    // ── 更新 UI ───────────────────────────────────────────
    function updateWalletUI() {
        const btn = document.getElementById("wallet-btn");
        if (!btn) return;
        if (currentAccount) {
            const short = currentAccount.slice(0, 6) + "..." + currentAccount.slice(-4);
            const status = safeAddress ? "✅" : "⏳";
            btn.textContent = `${status} ${short}`;
            btn.onclick = showWalletMenu;
        } else {
            btn.textContent = "👛 连接钱包";
            btn.onclick = connectWallet;
        }

        // 自动填充交易面板的钱包地址
        const walletInput = document.getElementById("trade-wallet");
        if (walletInput && currentAccount) {
            walletInput.value = safeAddress || currentAccount;
        }
    }

    // ── 钱包菜单 ──────────────────────────────────────────
    function showWalletMenu() {
        const actions = [
            safeAddress
                ? `Safe: ${safeAddress.slice(0,8)}...${safeAddress.slice(-4)}`
                : "部署 Safe 钱包（免 Gas）",
            "检查授权状态",
            "断开钱包",
        ];
        const choice = prompt(
            `钱包: ${currentAccount.slice(0,8)}...\n\n选择操作:\n1. ${actions[0]}\n2. ${actions[1]}\n3. ${actions[2]}\n\n输入数字:`,
            "1"
        );
        if (choice === "1") {
            safeAddress ? null : deploySafe();
        } else if (choice === "2") {
            checkSafeStatus();
        } else if (choice === "3") {
            disconnectWallet();
        }
    }

    // ── 断开 ──────────────────────────────────────────────
    function disconnectWallet() {
        currentAccount = null;
        safeAddress = null;
        updateWalletUI();
    }

    // ── Safe 状态检查 ─────────────────────────────────────
    async function checkSafeStatus() {
        if (!currentAccount) return;
        const btn = document.getElementById("wallet-btn");
        if (btn) btn.textContent = "⏳ 检查 Safe...";

        try {
            const resp = await fetch(`/api/wallet/status?eoa=${currentAccount}`);
            const data = await resp.json();

            if (data.safe_deployed && data.safe_address) {
                safeAddress = data.safe_address;
                const approvals = data.approvals || {};
                const allApproved = Object.values(approvals).every(v => v > 100);
                console.log("Safe:", safeAddress, "Approvals:", approvals);

                if (!allApproved) {
                    if (confirm("代币授权未完成，是否现在授权？（免 Gas）")) {
                        await approveTokens();
                    }
                }
            } else {
                safeAddress = null;
                if (confirm("尚未部署 Safe 钱包。是否现在部署？（免 Gas，由 dobguski Builder 赞助）")) {
                    await deploySafe();
                }
            }
        } catch (e) {
            console.error("Safe status check failed:", e);
        }
        updateWalletUI();
    }

    // ── 部署 Safe ─────────────────────────────────────────
    async function deploySafe() {
        if (!currentAccount) return;
        const btn = document.getElementById("wallet-btn");
        if (btn) btn.textContent = "⏳ 部署 Safe...";

        try {
            const resp = await fetch("/api/wallet/deploy", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ eoa_address: currentAccount }),
            });
            const data = await resp.json();
            if (data.success) {
                safeAddress = data.safe_address || data.data?.proxyAddress || data.data?.address;
                alert(`Safe 部署成功: ${safeAddress}`);
            } else {
                alert(`部署失败: ${data.error || "未知错误"}`);
            }
        } catch (e) {
            alert(`部署失败: ${e.message}`);
        }
        updateWalletUI();
    }

    // ── 授权代币 ─────────────────────────────────────────
    async function approveTokens() {
        if (!safeAddress) return;
        const btn = document.getElementById("wallet-btn");
        if (btn) btn.textContent = "⏳ 授权中...";

        try {
            const resp = await fetch("/api/wallet/approve", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ safe_address: safeAddress }),
            });
            const data = await resp.json();
            if (data.success) {
                alert("代币授权成功！现在可以下单交易了");
            } else {
                alert(`授权失败: ${data.error || "未知错误"}`);
            }
        } catch (e) {
            alert(`授权失败: ${e.message}`);
        }
        updateWalletUI();
    }

    // ── 账户切换监听 ──────────────────────────────────────
    if (typeof window.ethereum !== "undefined") {
        window.ethereum.on("accountsChanged", function (accounts) {
            currentAccount = accounts[0] || null;
            safeAddress = null;
            updateWalletUI();
        });
    }
})();
