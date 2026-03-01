"""
src/process/normalizer.py — 数据标准化工具

职责：把从不同 API 拿到的原始数据，转换成统一格式再落库。
"""


def normalize_address(addr: str) -> str:
    """地址统一转小写（方便和标签库对比）"""
    if not addr:
        return ""
    return addr.strip().lower()


def get_address_tag(addr: str, address_tags: dict) -> str:
    """
    根据地址标签库返回可读名称。
    找不到则返回缩略地址，例如 0x1234...5678
    """
    if not addr:
        return "Unknown"
    normalized = normalize_address(addr)
    if normalized in address_tags:
        return address_tags[normalized]
    return f"{addr[:8]}...{addr[-6:]}"


def wei_to_eth(wei_value: str) -> float:
    """
    将十六进制 wei 字符串转换为 ETH 浮点数。
    1 ETH = 10^18 wei
    例如：'0xde0b6b3a7640000' → 1.0
    """
    try:
        return int(wei_value, 16) / 10 ** 18
    except (ValueError, TypeError):
        return 0.0


def calc_usd_value(amount_eth: float, eth_price: float) -> float:
    """计算美元价值（保留两位小数）"""
    return round(amount_eth * eth_price, 2)
