# ACCEPTANCE_CHECKLIST — CryptoProject L2 消息面

> 验收时间：2026-03-02
> 验收范围：L2 新闻情绪接入 + Dashboard UI 重构

---

## ✅ PASS — 已完成且验证通过

### 新闻采集（news_feed）
- [x] `src/ingest/news_feed.py` 已创建，接入 NewsAPI
- [x] NEWSAPI_KEY 通过 `.env` + dotenv 加载，未硬编码
- [x] 单次宽泛查询（`bitcoin OR ethereum OR crypto`），控制 API 消耗（24次/天）
- [x] URL UNIQUE 约束去重，已验证重复插入静默跳过
- [x] `news_events` 表已建，当前 30 条记录
- [x] `system_health` 写入正常（`news_feed status=ok`）

### 情绪评分（sentiment_scoring）
- [x] `src/process/sentiment_scoring.py` 已创建
- [x] `score_headline("Bitcoin surges to record high")` → +1.0 ✅
- [x] `score_headline("Bitcoin crashes amid SEC ban")` → -1.0 ✅
- [x] `score_headline("Bitcoin traded at $95000")` → 0.0 ✅
- [x] `aggregate_scores([])` → 0.0 ✅（空列表安全处理）

### 情绪聚合（sentiment_feed）
- [x] 替换 `_fetch_news_score_placeholder` 为真实 DB 聚合
- [x] `sentiment_snapshots.news_score` 写入真实值（当前 -0.1）
- [x] F&G 分支与 news 分支各自独立，任一失败不影响另一个

### 策略过滤（signal_engine）
- [x] `apply_sentiment_filter` 新增 news_score 过滤层
- [x] `buy` 且 `news_score < -0.3` → `hold`，日志输出 `news_filter score=...`
- [x] `sell` 信号直接放行，不受 news_score 影响
- [x] F&G 过滤（极度贪婪）优先于 news 过滤，顺序正确

### 主程序（main.py）
- [x] dotenv 加载正常（`api_key_set=True`）
- [x] `news_feed` 线程启动（独立 daemon 线程）
- [x] trading 日志包含 `news=` 字段

### Dashboard 重构
- [x] K 线图、布林带、MA、RSI、周期切换 全部删除
- [x] CoinGecko OHLC API 调用已移除（页面轻量化）
- [x] 价格行：4 个币种当前价格 + 24h 涨跌显示正常
- [x] 策略状态卡：信号/来源/动作/F&G/news_score 展示
- [x] 执行状态卡：现金/持仓/权益/最近成交 展示
- [x] 消息面卡：F&G + news_score + 综合情绪（Bullish/Neutral/Bearish）
- [x] 新闻列表：最近10条 + 情绪分 + 颜色编码（绿正红负灰中性）
- [x] 链上大额事件：ETH 滑块筛选 + Etherscan 链接
- [x] 中文 / English 界面切换（右上角按钮，session_state 保持）
- [x] 30s 自动刷新

### 稳定性
- [x] NewsAPI 不配置 Key 时：仅打 warning，主循环不崩
- [x] Etherscan 失败时：onchain_feed 独立报错，不影响其他线程
- [x] 所有新增线程写 `system_health`

---

## ❌ FAIL — 未通过项

### onchain_feed（历史问题，已修复）
- [x] **已修复**：重启 main.py 后恢复正常（原因：旧进程未加载 ETHERSCAN_API_KEY）

---

## 📋 TODO — 后续可优化项

### 功能增强
- [ ] news_score 历史趋势图（折线图，在 dashboard 展示24h情绪变化）
- [ ] 按 symbol 分别展示 news_score（BTC 和 ETH 的新闻情绪往往不同）
- [ ] 新闻标题中文翻译（可选，接入翻译 API）
- [ ] 情绪词库持续扩充（当前约 80+80 个词，可加到 200+）

### 稳定性增强
- [ ] news_feed 失败重试机制（当前失败直接 sleep，下一轮再试）
- [ ] equity_curve 图表（折线图展示资金曲线变化）
- [ ] Dashboard `use_container_width` 警告修复（改为 `width='stretch'`）

### 策略增强
- [ ] news_score 与 F&G 加权综合打分（不是简单分步过滤）
- [ ] 分 symbol 的新闻情绪过滤（当前所有 symbol 共用同一个 news_score）

---

## 🔄 回归建议

下次验证时优先复测以下路径：

1. **重启后各模块全部 OK**：`python3 src/main.py` → 观察5条线程日志全部 `status=ok`
2. **news_filter 生效**：造一个 news_score < -0.3 的场景，确认 buy 信号被压为 hold
3. **Dashboard 语言切换**：点 EN 按钮后全界面切换，点中文恢复，刷新后保持
4. **onchain_feed 链上数据**：等待链上有大额交易，确认 `news_events` + `onchain_events` 同时有数据
