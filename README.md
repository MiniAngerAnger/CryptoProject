# CryptoProject V1 — 只读监控系统

> 实时采集 BTC/ETH 价格 + 链上大额交易，落库 SQLite，Streamlit 看板展示。
> **严禁实盘交易 / 自动下单。**

---

## 目录结构

```
CryptoProject/
├── src/
│   ├── ingest/
│   │   ├── price_feed.py      # BTC/ETH 价格采集（CoinGecko）
│   │   └── onchain_feed.py    # 链上大额交易监控（Etherscan）
│   ├── process/
│   │   └── normalizer.py      # 数据标准化工具
│   ├── storage/
│   │   └── db.py              # SQLite 数据库层
│   ├── dashboard/
│   │   └── app.py             # Streamlit 看板
│   └── main.py                # 采集主程序入口
├── configs/
│   └── settings.yaml          # 配置中心（阈值、间隔、地址标签）
├── db/
│   └── trading.db             # SQLite 文件（运行时自动创建）
├── data/
│   ├── raw/                   # 原始数据（预留）
│   └── processed/             # 处理后数据（预留）
├── whale_v2.py                # 旧版脚本（保留参考）
├── Whale_Archives/            # 旧版文件输出归档
├── requirements.txt
└── .env.example               # 环境变量模板
```

---

## 快速开始

### 1. 创建虚拟环境（唯一推荐命令）

```bash
cd /Users/moody/Downloads/MYAI/PROJECTS/CryptoProject
python3 -m venv .venv
source .venv/bin/activate
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 用编辑器打开 .env，填入真实 API Key
```

**必须设置的变量：**

| 变量名 | 说明 | 获取地址 |
|--------|------|---------|
| `ETHERSCAN_API_KEY` | Etherscan 链上数据 | https://etherscan.io/myapikey |

**方式一：写入 .env 文件（推荐）**
```bash
# .env 文件内容
ETHERSCAN_API_KEY=你的真实Key
```

**方式二：临时环境变量**
```bash
export ETHERSCAN_API_KEY=你的真实Key
```

### 4. 启动采集主程序（终端 1）

```bash
# 确保在项目根目录，虚拟环境已激活
source .venv/bin/activate
python3 src/main.py
```

正常输出示例：
```
2026-03-01 10:00:01 [INFO] 🚀 CryptoProject V1 采集系统启动
2026-03-01 10:00:01 [INFO] 数据库表初始化完成
2026-03-01 10:00:01 [INFO] ✅ 线程启动: price_feed
2026-03-01 10:00:01 [INFO] ✅ 线程启动: onchain_feed
2026-03-01 10:00:31 [INFO] [price_feed] BTC: $67,234.00
2026-03-01 10:00:31 [INFO] [price_feed] ETH: $3,521.00
```

### 5. 启动看板（终端 2）

```bash
source .venv/bin/activate
streamlit run src/dashboard/app.py
```

浏览器自动打开 `http://localhost:8501`

---

## 配置调整

编辑 `configs/settings.yaml`，无需改代码：

```yaml
onchain_feed:
  whale_threshold_eth: 50    # 把阈值改为 50 ETH

price_feed:
  interval_seconds: 60       # 改为每分钟采集一次
```

---

## 常见报错排查

| 报错 | 原因 | 解决 |
|------|------|------|
| `ModuleNotFoundError: No module named 'yaml'` | 依赖未安装 | `pip install -r requirements.txt` |
| `ModuleNotFoundError: No module named 'streamlit'` | 同上 | 同上 |
| `[onchain_feed] ETHERSCAN_API_KEY 未设置` | 环境变量缺失 | 配置 `.env` 或 `export` |
| `CoinGecko 价格请求失败: 429` | API 限速 | 将 `interval_seconds` 改为 60 |
| `OperationalError: unable to open database file` | db/ 目录不存在 | `mkdir -p db` |
| 看板显示"采集中..." | 采集器还未运行 | 先启动 `python3 src/main.py` |

---

## 数据库表结构

```sql
price_ticks      -- BTC/ETH 价格快照
onchain_events   -- 链上大额交易（>= 阈值）
system_health    -- 模块运行状态日志
```

---

## V1.5 新增：Paper Trading 闭环（实验版）

已新增：
- `strategy/signal_engine.py`：baseline / kronos / hybrid 信号模式 + sentiment 过滤
- `execution/paper_broker.py`：模拟下单、仓位、资金曲线
- `risk/risk_guard.py`：单笔仓位和最小下单金额风控
- `storage/db.py`：新增 `orders` / `fills` / `positions` / `equity_curve` / `sentiment_snapshots` 表
- `ingest/sentiment_feed.py`：Fear & Greed 指数采集（L1）+ 新闻情绪预留接口

配置入口：`configs/settings.yaml`
- `trading.*`
- `strategy.*`
- `kronos.*`
- `paper_trading.*`
- `risk.*`

> 默认 `kronos.enabled=false`，即使未安装 Kronos 依赖也可稳定运行（自动降级 baseline）。

## V1.1 建议迭代方向

- 增加 Telegram / 企业微信告警推送
- 支持多链（BSC、Arbitrum）
- 价格折线图增加均线指标
- 添加历史数据导出（CSV）

---

*严禁自动下单 | 仅用于学习和监控 | API Key 永远不要提交到 Git*
