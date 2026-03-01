import requests
import time
import os
import yfinance as yf
from datetime import datetime

# --- 【1. 自动化配置区】 ---
SAVE_DIR = "/Users/moody/Downloads/MY AI/CryptoProject/Whale_Archives"
WHALE_THRESHOLD = 100  # 监控阈值：100 ETH
# 你的专属 Etherscan V2 专线
API_KEY = os.getenv("ETHERSCAN_API_KEY", "")
ETH_RPC_URL = f"https://api.etherscan.io/v2/api?chainid=1&apikey={API_KEY}"

# 核心地址库（自动打标签）
ADDRESS_TAGS = {
    "0x4dbd4fc535ac27206064b68ffcf827b0a60bab3f": "🔶 币安-14 (Binance)",
    "0x28c6c06298d514db089934071355e5743bf21d60": "🔶 币安-热钱包",
    "0xdfd5293d8e347dfe59e90efd55b2956a1343963d": "💎 OKX-热钱包",
    "0x30273063529244030704423c46c1a4a870845b2e": "🐳 Upbit-巨鲸",
    "0x46456e20703f8f6ef8b6a70a8d79389369324021": "🏦 Jump Trading"
}

# --- 【2. 功能函数】 ---
def get_eth_price():
    try:
        eth = yf.Ticker("ETH-USD")
        return eth.fast_info['last_price']
    except:
        return 2500.0

def get_tag(address):
    if not address: return "Unknown"
    addr_lower = address.lower()
    return ADDRESS_TAGS.get(addr_lower, f"{address[:8]}...{address[-6:]}")

def save_to_obsidian(tx_hash, sender, receiver, amount, eth_price):
    if not os.path.exists(SAVE_DIR):
        os.makedirs(SAVE_DIR)
    
    usd_value = amount * eth_price
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    filename = f"Whale_{tx_hash[:10]}.md"
    filepath = os.path.join(SAVE_DIR, filename)
    
    content = f"""---
amount_eth: {amount:.2f}
usd_value: {usd_value:,.0f}
from: "{sender}"
to: "{receiver}"
timestamp: {timestamp}
---
### 🚨 巨鲸交易摘要
- **转账金额**: `{amount:.2f} ETH`
- **美元价值**: `${usd_value:,.0f} USD` (单价: ${eth_price:.2f})
- **发送方**: [[{sender}|{get_tag(sender)}]]
- **接收方**: [[{receiver}|{get_tag(receiver)}]]
- **交易哈希**: [查看 Etherscan](https://etherscan.io/tx/{tx_hash})
"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ 捕获成功: {amount:.2f} ETH (${usd_value:,.0f})")

# --- 【3. 监控主逻辑】 ---
def monitor_whale():
    print("🚀 巨鲸雷达【专线版】已启动")
    last_block = 0
    while True:
        try:
            eth_price = get_eth_price()
            # 获取最新区块号
            params = {"module": "proxy", "action": "eth_blockNumber"}
            res = requests.get(ETH_RPC_URL, params=params).json()
            
            if 'result' not in res:
                print(f"⚠️ 专线响应异常: {res}")
                time.sleep(5)
                continue
                
            current_block = int(res['result'], 16)
            
            if current_block > last_block:
                if last_block != 0:
                    print(f"📦 正在扫描新区块: {current_block} | ETH: ${eth_price:.2f}")
                
                # 获取区块详情
                params = {"module": "proxy", "action": "eth_getBlockByNumber", "tag": hex(current_block), "boolean": "true"}
                block_res = requests.get(ETH_RPC_URL, params=params).json()
                
                if 'result' not in block_res or not block_res['result']:
                    continue
                
                transactions = block_res['result'].get('transactions', [])
                for tx in transactions:
                    # 排除合约调用，只看转账
                    if tx.get('value') and tx['value'] != '0x0':
                        value_eth = int(tx['value'], 16) / 10**18
                        if value_eth >= WHALE_THRESHOLD:
                            save_to_obsidian(tx['hash'], tx['from'], tx['to'], value_eth, eth_price)
                
                last_block = current_block
            
            # Etherscan 免费版 API 每秒限制 5 次，我们设置 5 秒轮询一次非常安全
            time.sleep(5)
        except Exception as e:
            print(f"❌ 出错: {e}")
            time.sleep(5)

if __name__ == "__main__":
    monitor_whale()