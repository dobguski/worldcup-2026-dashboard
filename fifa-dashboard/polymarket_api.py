"""
Polymarket CLOB API 客户端
==========================
HMAC 签名 + 下单 + Builder 归因
参考: docs.polymarket.com CLOB API / @polymarket/builder-signing-sdk
"""
import hashlib
import hmac
import json
import time
import base64
import urllib.request
import urllib.error

CLOB_API_BASE = "https://clob.polymarket.com"


def build_hmac_signature(secret_b64: str, timestamp_ms: int, method: str, path: str, body: str = "") -> str:
    """
    构建 HMAC-SHA256 签名
    secret_b64: Base64 编码的密钥
    签名内容: timestamp + method + path + body
    """
    secret_bytes = base64.b64decode(secret_b64)
    message = f"{timestamp_ms}{method}{path}{body}"
    sig = hmac.new(secret_bytes, message.encode("utf-8"), hashlib.sha256).hexdigest()
    return sig


def clob_request(
    method: str,
    path: str,
    api_key: str,
    secret_b64: str,
    passphrase: str,
    wallet_address: str,
    body: dict | None = None,
    base_url: str = CLOB_API_BASE,
) -> dict:
    """
    发送经过 HMAC 签名的 CLOB API 请求
    返回 (status_code, response_dict)
    """
    body_str = json.dumps(body) if body else ""
    timestamp_ms = int(time.time() * 1000)

    signature = build_hmac_signature(secret_b64, timestamp_ms, method, path, body_str)

    headers = {
        "POLY_ADDRESS": wallet_address,
        "POLY_API_KEY": api_key,
        "POLY_PASSPHRASE": passphrase,
        "POLY_SIGNATURE": signature,
        "POLY_TIMESTAMP": str(timestamp_ms),
        "Content-Type": "application/json",
        "User-Agent": "DobGuski-FIFA-Dashboard/0.2",
    }

    url = f"{base_url}{path}"
    data = body_str.encode("utf-8") if body_str else None

    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
            return {"success": True, "status": resp.status, "data": result}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else str(e)
        return {"success": False, "status": e.code, "error": error_body}
    except urllib.error.URLError as e:
        return {"success": False, "status": 0, "error": str(e.reason)}


def place_order(
    token_id: str,
    price: float,
    size: float,
    side: str,  # "BUY" or "SELL"
    api_key: str,
    secret_b64: str,
    passphrase: str,
    wallet_address: str,
    builder_code: str,
    order_type: str = "GTC",
) -> dict:
    """
    向 CLOB API 提交带 Builder 归因的订单

    参数:
        token_id: Polymarket 代币 ID (如 "0x1234...")
        price: 价格 (0.00 - 1.00 USDC)
        size: 数量 (USDC)
        side: "BUY" 或 "SELL"
        builder_code: Builder Code (bytes32)
        order_type: "GTC" | "GTD" | "FOK" | "FAK"
    """
    # 价格和数量向上取整到合适精度
    price = round(price, 4)
    size = round(size, 2)

    order_payload = {
        "tokenID": token_id,
        "price": price,
        "size": size,
        "side": side,
        "orderType": order_type,
        "builderCode": builder_code,  # ← Builder 归因关键字段
    }

    return clob_request(
        method="POST",
        path="/order",
        api_key=api_key,
        secret_b64=secret_b64,
        passphrase=passphrase,
        wallet_address=wallet_address,
        body=order_payload,
    )


def get_order_book(token_id: str) -> dict:
    """获取订单簿（无需认证）"""
    return clob_request(
        method="GET",
        path=f"/book?token_id={token_id}",
        api_key="", secret_b64="", passphrase="", wallet_address="",
    )


def get_midpoint(token_id: str) -> dict:
    """获取中间价（无需认证）"""
    return clob_request(
        method="GET",
        path=f"/midpoint?token_id={token_id}",
        api_key="", secret_b64="", passphrase="", wallet_address="",
    )
