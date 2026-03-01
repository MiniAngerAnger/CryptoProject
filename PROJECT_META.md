# PROJECT_META.md

## 项目名
CryptoProject

## 目标
监控部分 ETH 巨鲸地址的大额转账，并结合市场数据做简单记录与观察。

## 输入
- CoinGecko 价格数据（BTC/ETH/SOL/BNB）
- Etherscan 链上交易数据
- Alternative.me Fear & Greed 指数
- NewsAPI 新闻标题（可选，需 NEWSAPI_KEY）

## 输出
- SQLite：price_ticks / onchain_events / news_events / sentiment_snapshots / orders / fills / positions / equity_curve
- Streamlit 执行控制台（策略、执行、消息面、链上事件）

## 运行方式
cd PROJECTS/CryptoProject；python3 -m venv venv；source venv/bin/activate  # Windows 使用 venv\\Scripts\\activate

## 依赖
Python、Gemini API

## 当前状态
稳定运行（V1.5 + L2 消息面）

## 风险与限制
未知

## 下一步（1-3条）
1. 消息面按币种拆分 news_score（BTC/ETH/SOL/BNB）
2. 增加权益曲线与情绪趋势图（Dashboard）
3. 补充回测与验收脚本（自动化）
