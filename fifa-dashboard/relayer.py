"""
Polymarket Builder Relayer 客户端
==================================
Safe 钱包部署、代币授权、元交易提交
基于 Builder API 凭证，为用户提供免 Gas 体验
"""
import json
import time
import base64
import hashlib
import hmac
import urllib.request
import urllib.error

RELAYER_BASE = "https://relayer-v2.polymarket.com"
POLYGON_CHAIN_ID = 137

# Polygon 合约地址
CTF_EXCHANGE = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
NEG_RISK_CTF = "0xC5d563A36AE78145C45a50134d48A1215220f80a"
NEG_RISK_ADAPTER = "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296"
USDC = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"


def build_relayer_signature(secret_b64: str, timestamp_ms: int, method: str, path: str, body: str = "") -> str:
    """构建 Relayer HMAC 签名"""
    secret_bytes = base64.b64decode(secret_b64)
    message = f"{timestamp_ms}{method}{path}{body}"
    return hmac.new(secret_bytes, message.encode("utf-8"), hashlib.sha256).hexdigest()


def relayer_request(method: str, path: str, api_key: str, secret_b64: str,
                    passphrase: str, body: dict | None = None) -> dict:
    """发送经过 Builder 签名的 Relayer API 请求"""
    body_str = json.dumps(body) if body else ""
    timestamp_ms = int(time.time() * 1000)
    signature = build_relayer_signature(secret_b64, timestamp_ms, method, path, body_str)

    headers = {
        "POLY_BUILDER_API_KEY": api_key,
        "POLY_BUILDER_SIGNATURE": signature,
        "POLY_BUILDER_TIMESTAMP": str(timestamp_ms),
        "POLY_BUILDER_PASSPHRASE": passphrase,
        "Content-Type": "application/json",
        "User-Agent": "DobGuski-Relayer/0.1",
    }

    url = f"{RELAYER_BASE}{path}"
    data = body_str.encode("utf-8") if body_str else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            result = json.loads(resp.read().decode())
            return {"success": True, "status": resp.status, "data": result}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else str(e)
        return {"success": False, "status": e.code, "error": error_body[:300]}
    except Exception as e:
        return {"success": False, "status": 0, "error": str(e)[:300]}


def deploy_safe(eoa_address: str, api_key: str, secret_b64: str, passphrase: str) -> dict:
    """为用户 EOA 部署 Gnosis Safe 代理钱包"""
    payload = {
        "owner": eoa_address,
        "chainId": POLYGON_CHAIN_ID,
    }
    return relayer_request("POST", "/deploy", api_key, secret_b64, passphrase, payload)


def get_safe_status(eoa_address: str, api_key: str, secret_b64: str, passphrase: str) -> dict:
    """查询 Safe 部署状态"""
    return relayer_request("GET", f"/safe?owner={eoa_address}&chainId={POLYGON_CHAIN_ID}",
                           api_key, secret_b64, passphrase)


def execute_batch(transactions: list, safe_address: str, api_key: str,
                  secret_b64: str, passphrase: str) -> dict:
    """通过 Relayer 批量执行交易（免 Gas）"""
    payload = {
        "safe": safe_address,
        "transactions": transactions,
        "chainId": POLYGON_CHAIN_ID,
    }
    return relayer_request("POST", "/execute", api_key, secret_b64, passphrase, payload)


def build_approval_txs(safe_address: str) -> list:
    """构建 USDC 和 Outcome Token 授权交易列表"""
    txs = []

    # USDC 授权给 CTF Exchange
    txs.append({
        "to": USDC,
        "value": "0",
        "data": ("0x095ea7b3" +
                 CTF_EXCHANGE[2:].lower().rjust(64, "0") +
                 "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"),
    })

    # USDC 授权给 Neg Risk CTF
    txs.append({
        "to": USDC,
        "value": "0",
        "data": ("0x095ea7b3" +
                 NEG_RISK_CTF[2:].lower().rjust(64, "0") +
                 "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"),
    })

    # USDC 授权给 Neg Risk Adapter
    txs.append({
        "to": USDC,
        "value": "0",
        "data": ("0x095ea7b3" +
                 NEG_RISK_ADAPTER[2:].lower().rjust(64, "0") +
                 "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"),
    })

    return txs


def check_allowance(owner: str, spender: str, rpc_url: str = "https://rpc.ankr.com/polygon") -> dict:
    """检查 USDC 授权额度"""
    data = ("0xdd62ed3e" +
            owner[2:].lower().rjust(64, "0") +
            spender[2:].lower().rjust(64, "0"))
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "eth_call",
        "params": [{"to": USDC, "data": data}, "latest"],
    }
    req = urllib.request.Request(rpc_url,
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            raw = result.get("result", "0x0")
            allowance = int(raw, 16) / 1e6 if raw and raw != "0x" else 0
            return {"success": True, "allowance": allowance, "spender": spender}
    except Exception as e:
        return {"success": False, "error": str(e)}
