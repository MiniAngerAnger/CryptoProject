# CryptoProject — 区块链巨鲸监控实验

> 监控部分 ETH 巨鲸地址的大额转账，并结合市场数据做简单记录与观察。

---

## 1. 快速开始

### 1.1 虚拟环境（可选）

```bash
cd PROJECTS/CryptoProject
python3 -m venv venv
source venv/bin/activate  # Windows 使用 venv\\Scripts\\activate
```

### 1.2 安装依赖

根据 `DEVELOPMENT_STORY.md` / 代码注释中的说明安装 requests、yfinance 等依赖。

### 1.3 配置 API Key

- 环境变量：`ETHERSCAN_API_KEY` / `BINANCE_API_KEY` / `BINANCE_SECRET_KEY` / `GEMINI_API_KEY`

按照文件中的格式填入自己的密钥（注意：不要把真 `.env` 提交到 Git 仓库）。

### 1.4 运行脚本

```bash
python3 whale_v2.py
```

脚本会轮询鲸鱼地址、记录交易，并根据规则输出结果。

---

## 2. 项目结构（简要）

```text
CryptoProject/
├── whale_v2.py             # 主脚本
├── Whale_Archives/         # 历史鲸鱼地址数据
├── DEVELOPMENT_STORY.md    # 开发故事记录
├── LEARNING_NOTES.md       # 学习记录
├── .env.example            # 环境变量模板（不含真实密钥）
└── whale_v2.py             # 主脚本
```

---

## 3. 相关学习

- Learning 阶段文档：`Learning/Phase_05_CryptoProject_实时监控.md`

