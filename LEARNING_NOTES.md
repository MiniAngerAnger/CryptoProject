# 📚 以太坊巨鲸监控 — 项目技术学习笔记

> 定位：零基础入门者的项目复盘讲解
> 案例项目：`CryptoProject`（以太坊大额交易实时监控）
> 作者：Moo | 讲解：Claude（你的编程老师）

---

## 一、项目是做什么的？

一个 Python 脚本，**实时监控以太坊区块链上的大额交易**（≥100 ETH），发现巨鲸动了就自动记录到 Obsidian 笔记。

核心功能：
- 每 5 秒扫描最新的以太坊区块
- 筛选出 ≥ 100 ETH 的交易（约 30 万美元+）
- 自动识别已知地址（币安、OKX、Jump Trading 等）
- 获取实时 ETH/USD 价格
- 生成 Markdown 笔记存入 Obsidian

---

## 二、用了哪些编程语言？

| 语言 | 用在哪里 |
|------|---------|
| **Python** | 全部逻辑（API 调用、数据处理、文件生成） |

> 💡 **关键点**：核心代码只有 **109 行**。这可能是所有项目里最短的——但它涉及的概念（区块链、API、实时监控、自动化文档）一点都不少。

---

## 三、项目架构是什么？

```
CryptoProject/
├── whale_v2.py          → 核心脚本（109行，就这么短）
├── Whale_Archives/      → 巨鲸交易记录（Obsidian 笔记）
│   ├── Whale_0xdcb652.md
│   ├── Whale_0x6b2a5c.md
│   └── ... （共 30 条记录）
├── .obsidian/           → Obsidian 配置
└── .env                 → API 密钥
```

数据流：

```
Etherscan API  →  whale_v2.py  →  Markdown 文件
（区块链数据）     （筛选+标记）    （Obsidian 笔记）
                      ↑
               Yahoo Finance
               （ETH/USD 价格）
```

> 💡 **架构核心思想**：监控类项目的经典模式——**轮询**（Polling）。每隔固定时间去检查一次有没有新数据，有就处理，没有就等下一次。简单但有效。

---

## 四、用了哪些技术？

### 4.1 Etherscan API — 以太坊区块链的"搜索引擎"

**官网**：https://etherscan.io/apis
**作用**：查询以太坊区块链上的交易、地址、区块等信息。

```python
import requests

API_KEY = "你的Etherscan_API_Key"
BASE_URL = "https://api.etherscan.io/v2/api"

# 1. 获取最新区块号
response = requests.get(BASE_URL, params={
    "chainid": 1,                    # 1 = 以太坊主网
    "module": "proxy",
    "action": "eth_blockNumber",     # 获取最新区块号
    "apikey": API_KEY
})
block_hex = response.json()["result"]       # 返回十六进制："0x12a3b4c"
block_number = int(block_hex, 16)           # 转十进制：19546956

# 2. 获取该区块的所有交易
response = requests.get(BASE_URL, params={
    "chainid": 1,
    "module": "proxy",
    "action": "eth_getBlockByNumber",
    "tag": block_hex,               # 用十六进制区块号
    "boolean": "true",              # true = 包含完整交易数据
    "apikey": API_KEY
})
block = response.json()["result"]
transactions = block["transactions"]  # 这个区块里的所有交易
```

> 💡 **学习重点**：区块链的数据是公开的——你不需要任何人的许可就能查看任何交易。Etherscan 只是帮你方便地查询这些公开数据。`int(hex_string, 16)` 是十六进制转十进制的方法。

---

### 4.2 区块链基础概念

```
区块链就像一本公开的账本：

区块 #19546956
├── 交易 1: 0xABC... → 0xDEF...  (0.5 ETH)
├── 交易 2: 0x123... → 0x456...  (134.26 ETH)  ← 巨鲸！
├── 交易 3: 0x789... → 0xABC...  (0.01 ETH)
└── ... （一个区块里可能有几百笔交易）

区块 #19546957
├── ... （下一个区块，大约 12 秒后生成）
```

| 概念 | 解释 | 类比 |
|------|------|------|
| 区块（Block） | 一批交易打包在一起 | 账本的一页 |
| 区块号 | 区块的序号 | 页码 |
| 交易（Transaction） | 一笔转账记录 | 账本上的一行 |
| 地址（Address） | 钱包的标识 | 银行账号 |
| ETH | 以太坊的原生货币 | 钱 |
| Wei | ETH 的最小单位（1 ETH = 10^18 Wei） | 分（1元 = 100分） |

---

### 4.3 Wei 转 ETH

```python
# 区块链上的金额单位是 Wei（整数），需要转成 ETH（小数）
def wei_to_eth(wei_hex):
    """十六进制 Wei → ETH"""
    wei = int(wei_hex, 16)          # "0x56bc75e2d63100000" → 100000000000000000000
    eth = wei / 1e18                # ÷ 10^18 → 100.0
    return eth

# 示例
value_hex = "0x56bc75e2d63100000"   # 交易里的金额（十六进制 Wei）
eth_amount = wei_to_eth(value_hex)   # 100.0 ETH
```

> 💡 **学习重点**：为什么用 Wei 不直接用 ETH？因为区块链不支持小数运算（浮点数有精度问题）。用最小单位的整数来表示金额，和"人民币用分而不是元来计算"是一个道理。`1e18` 是 Python 里 10 的 18 次方的科学计数法写法。

---

### 4.4 yfinance — 实时价格

```python
import yfinance as yf

def get_eth_price():
    """获取 ETH 的美元价格"""
    try:
        ticker = yf.Ticker("ETH-USD")
        data = ticker.history(period="1d")
        if not data.empty:
            return float(data['Close'].iloc[-1])  # 最新收盘价
    except Exception:
        return 2800.0  # API 失败时的兜底价格
```

> 💡 **学习重点**：`yfinance` 是 Yahoo Finance 的非官方 Python 库，不需要 API Key。`iloc[-1]` 是 pandas 的"取最后一行"语法。兜底价格是"优雅降级"——API 挂了也不影响程序运行。

---

### 4.5 地址标签系统

```python
KNOWN_ADDRESSES = {
    "0x4dbd4fc535ac27206064b68ffcf827b0a60bab3f": "🔶 币安-14",
    "0x28c6c06298d514db089934071355e5743bf21d60": "🔶 币安-热钱包",
    "0xdfd5293d8e347dfe59e90efd55b2956a1343963d": "💎 OKX-热钱包",
    "0x30270942208c8b25f5e44b2c724c40fcc3d789a2": "🐳 Upbit-巨鲸",
    "0x46450813c885523c5e7fe2e1a70d14e71e5ef621": "🏦 Jump Trading",
}

def get_tag(address):
    """查地址标签，未知返回地址缩写"""
    address = address.lower()  # 地址不区分大小写
    if address in KNOWN_ADDRESSES:
        return KNOWN_ADDRESSES[address]
    return f"{address[:6]}...{address[-4:]}"  # 缩写："0xabcd...ef12"
```

> 💡 **学习重点**：`dict` 查找是 O(1) 复杂度——不管有多少已知地址，查找速度都是一样的。`address[:6]` 取前 6 个字符，`address[-4:]` 取后 4 个字符——这是区块链世界里地址缩写的通用格式。

---

## 五、核心逻辑：监控循环

```python
def monitor_whale():
    """主监控循环"""
    last_block = None  # 记住上一个处理过的区块

    while True:
        try:
            # 1. 获取最新区块号
            current_block = get_latest_block()

            # 2. 如果是新区块，处理它
            if current_block != last_block:
                transactions = get_block_transactions(current_block)

                # 3. 遍历所有交易，找巨鲸
                for tx in transactions:
                    eth_amount = wei_to_eth(tx["value"])
                    if eth_amount >= WHALE_THRESHOLD:  # ≥ 100 ETH
                        # 4. 找到巨鲸！获取价格，生成报告
                        usd_price = get_eth_price()
                        usd_value = eth_amount * usd_price
                        save_to_obsidian(tx, eth_amount, usd_value)
                        print(f"🐳 发现巨鲸！{eth_amount:.2f} ETH (${usd_value:,.0f})")

                last_block = current_block

        except Exception as e:
            print(f"错误: {e}")

        time.sleep(5)  # 每 5 秒检查一次
```

> 💡 **学习重点**：这是"轮询监控"的标准模板——`while True` 无限循环 + `time.sleep()` 控制频率 + `try/except` 防止单次错误导致整个程序崩溃。`last_block` 记录上一次处理的区块号，避免重复处理。

---

## 六、自动生成 Obsidian 笔记

```python
def save_to_obsidian(tx, eth_amount, usd_value):
    """把巨鲸交易保存为 Markdown 文件"""
    tx_hash = tx["hash"][:10]  # 取交易哈希前10位做文件名
    filename = f"Whale_{tx_hash}.md"

    content = f"""---
amount: {eth_amount:.2f} ETH
usd_value: ${usd_value:,.0f}
from: {get_tag(tx['from'])}
to: {get_tag(tx['to'])}
timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
---

# 🐳 巨鲸交易记录

**金额**: {eth_amount:.2f} ETH (${usd_value:,.0f})
**发送方**: {get_tag(tx['from'])}
**接收方**: {get_tag(tx['to'])}
**链接**: [Etherscan](https://etherscan.io/tx/{tx['hash']})
"""

    filepath = os.path.join(SAVE_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
```

> 💡 **学习重点**：`---` 包裹的部分叫 **YAML front matter**——Obsidian 用它来存储笔记的元数据（金额、时间等），可以用来搜索和过滤。`f"""..."""` 是 Python 的多行格式化字符串，非常适合生成模板化的内容。

---

## 七、知识点速查表

| 概念 | 一句话 | 类比 |
|------|--------|------|
| 区块链 | 公开的、不可篡改的交易账本 | 全世界都能看的银行流水 |
| ETH | 以太坊的原生代币 | 以太坊世界的"钱" |
| Wei | ETH 的最小单位（1 ETH = 10^18 Wei） | 1 元 = 100 分 |
| 区块 | 一批交易打包在一起 | 账本的一页 |
| 巨鲸（Whale） | 持有大量加密货币的地址 | 股市里的"大户" |
| Etherscan | 以太坊区块链浏览器 | 区块链的"百度" |
| 轮询（Polling） | 每隔一段时间检查一次 | 每 5 分钟刷新一次网页 |
| YAML front matter | Markdown 文件头的元数据 | 书的目录页 |
| 十六进制 | 0-9 + A-F 的计数方式 | 区块链数据的"母语" |
| int(hex, 16) | 十六进制转十进制 | 翻译 |

---

## 八、如果你想继续学，推荐路径

```
Level 1（已掌握）
  ✅ API 调用（requests）
  ✅ JSON 数据解析
  ✅ 文件自动生成（Markdown）
  ✅ 基本的轮询监控模式

Level 2（下一步）
  → WebSocket 实时推送（不用轮询，有新区块自动通知）
  → 数据库存储（SQLite / PostgreSQL 存历史记录）
  → 更多链的支持（BSC、Polygon、Solana）

Level 3（进阶方向）
  → 链上数据分析（追踪资金流向）
  → 聪明钱跟踪（分析巨鲸的历史胜率）
  → Telegram/Discord 实时推送

Level 4（产品化）
  → Web 仪表盘（可视化巨鲸动态）
  → 多链聚合监控
  → 预警系统（巨鲸异常行为检测）
```

---

> 📌 **最重要的一句话**：区块链最大的特点是**透明**——所有数据都是公开的。这个项目的 109 行代码做的事情，本质上就是"读公开数据 + 筛选 + 记录"。你用同样的思路，可以监控任何区块链上的任何类型的交易。

---

*本笔记由 Claude 根据实际开发过程整理，2026年2月*
