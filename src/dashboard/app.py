"""
src/dashboard/app.py — CryptoProject · 执行控制台

布局（单页，无 K 线，纯数据驱动）：
  - 顶栏：品牌 + 模块在线状态
  - 价格行：BTC/ETH/SOL/BNB 当前价格 + 24h 涨跌（紧凑型）
  - 策略 & 执行：当前信号 | 持仓 / 权益 / 最近成交
  - 消息面：F&G + news_score + 综合情绪 + 最近10条新闻
  - 链上事件：大额转账列表

K 线由 TradingView 等专业工具查看，本面板专注执行状态。
"""

import sys
import yaml
import pandas as pd
import streamlit as st
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from src.storage import db

# ─── 页面配置 ─────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CryptoProject 执行控制台",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
html, body, .stApp { background:#0b0e11 !important; color:#eaecef; }
[data-testid="stSidebar"] { background:#131722; }
[data-testid="stHeader"]     { display:none !important; }
[data-testid="stToolbar"]    { display:none !important; }
[data-testid="stDecoration"] { display:none !important; }
#MainMenu { display:none !important; }
footer    { display:none !important; }

.block-container {
    padding-top: 6px !important;
    padding-bottom: 60px !important;
    max-width: 100% !important;
}

/* 顶部状态栏 */
.topbar {
    display:flex; justify-content:space-between; align-items:center;
    background:#131722; border-bottom:1px solid #1e2329;
    padding:6px 20px; font-size:.78rem; color:#848e9c;
    margin-bottom:12px;
}
.topbar .brand { color:#f0b90b; font-weight:700; font-size:.9rem; letter-spacing:1px; }
.status-ok  { color:#0ecb81; }
.status-err { color:#f6465d; }

/* 价格条 */
.price-bar {
    display:flex; gap:0; background:#131722;
    border:1px solid #1e2329; border-radius:6px;
    padding:0; margin-bottom:16px; overflow:hidden;
}
.price-item {
    flex:1; padding:10px 16px; border-right:1px solid #1e2329;
}
.price-item:last-child { border-right:none; }
.pi-sym  { font-size:.7rem; color:#848e9c; font-weight:600; letter-spacing:.5px; }
.pi-price{ font-size:1.15rem; font-weight:700; color:#eaecef; margin:2px 0; }
.pi-up   { color:#0ecb81; font-size:.8rem; font-weight:600; }
.pi-dn   { color:#f6465d; font-size:.8rem; font-weight:600; }

/* 区块卡片 */
.card {
    background:#131722; border:1px solid #1e2329;
    border-radius:6px; padding:14px 16px; margin-bottom:16px;
}
.card-title {
    font-size:.7rem; font-weight:600; color:#848e9c;
    text-transform:uppercase; letter-spacing:1.2px; margin-bottom:12px;
}

/* 信号徽章 */
.sig-buy  { color:#0b0e11; background:#0ecb81; padding:3px 12px;
            border-radius:4px; font-weight:700; font-size:.95rem; }
.sig-sell { color:#0b0e11; background:#f6465d; padding:3px 12px;
            border-radius:4px; font-weight:700; font-size:.95rem; }
.sig-hold { color:#eaecef; background:#2b3139; padding:3px 12px;
            border-radius:4px; font-weight:700; font-size:.95rem; }

/* 数值标签 */
.kv-row  { display:flex; justify-content:space-between;
           padding:4px 0; border-bottom:1px solid #1e2329; font-size:.82rem; }
.kv-row:last-child { border-bottom:none; }
.kv-label{ color:#848e9c; }
.kv-val  { color:#eaecef; font-weight:600; }
.kv-up   { color:#0ecb81; font-weight:600; }
.kv-dn   { color:#f6465d; font-weight:600; }

/* 综合情绪大字 */
.composite-bull { font-size:1.2rem; font-weight:700; color:#0ecb81; }
.composite-bear { font-size:1.2rem; font-weight:700; color:#f6465d; }
.composite-neu  { font-size:1.2rem; font-weight:700; color:#848e9c; }

/* 新闻条目 */
.news-row {
    padding:6px 0; border-bottom:1px solid #1e2329;
    display:flex; gap:10px; align-items:flex-start; font-size:.78rem;
}
.news-row:last-child { border-bottom:none; }
.news-score-pos { color:#0ecb81; font-weight:700; min-width:40px; text-align:right; }
.news-score-neg { color:#f6465d; font-weight:700; min-width:40px; text-align:right; }
.news-score-neu { color:#848e9c; font-weight:700; min-width:40px; text-align:right; }
.news-title { color:#eaecef; flex:1; line-height:1.4; }
.news-meta  { color:#848e9c; font-size:.7rem; }

/* dataframe 覆盖 */
[data-testid="stDataFrame"] { border-radius:4px; }
</style>
""", unsafe_allow_html=True)

# ─── 资源加载（只连一次 DB）──────────────────────────────────────────────────
@st.cache_resource
def load_resources():
    cfg_path = PROJECT_ROOT / "configs" / "settings.yaml"
    with open(cfg_path, "r", encoding="utf-8") as f:
        settings = yaml.safe_load(f)
    conn = db.get_connection(settings["database"]["path"])
    db.init_tables(conn)
    return settings, conn

settings, conn = load_resources()
address_tags = settings.get("address_tags", {})
symbols = settings["price_feed"]["symbols"]

def get_tag(addr):
    if not addr:
        return "Unknown"
    return address_tags.get(addr.lower(), f"{addr[:8]}…{addr[-6:]}")

# ─── 辅助：综合情绪判断 ────────────────────────────────────────────────────────
def composite_sentiment(fg_value, news_score):
    """结合 F&G 和 news_score 输出综合情绪标签及样式类"""
    fg_bull = fg_value is not None and fg_value > 55
    fg_bear = fg_value is not None and fg_value < 45
    news_bull = news_score is not None and news_score > 0.1
    news_bear = news_score is not None and news_score < -0.1

    bull = sum([fg_bull, news_bull])
    bear = sum([fg_bear, news_bear])

    if bull >= 2:
        return "Bullish", "composite-bull", "↑"
    if bear >= 2:
        return "Bearish", "composite-bear", "↓"
    if bull > bear:
        return "Neutral / 偏多", "composite-neu", "→"
    if bear > bull:
        return "Neutral / 偏空", "composite-neu", "→"
    return "Neutral", "composite-neu", "—"

# ═══════════════════════════════════════════════════════════════════════════════
# 数据查询
# ═══════════════════════════════════════════════════════════════════════════════
health      = db.query_latest_health(conn)
health_map  = {r["module"]: r for r in health}
sent        = db.query_latest_sentiment(conn)
equity_row  = db.query_latest_equity(conn)
recent_news = db.query_news_events(conn, limit=10)
orders      = db.query_recent_orders(conn, limit=5)
whale_evts  = db.query_onchain_events(conn, limit=20, min_eth=0)

# ─── 顶部状态栏 ────────────────────────────────────────────────────────────────
def hstatus(module):
    r = health_map.get(module)
    if not r:
        return f"<span class='status-err'>✕ {module}</span>"
    cls = "status-ok" if r["status"] == "ok" else "status-err"
    dot = "●" if r["status"] == "ok" else "✕"
    return f"<span class='{cls}'>{dot} {module}</span>"

now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
st.markdown(f"""
<div class="topbar">
  <span class="brand">⚡ CRYPTO EXEC CONSOLE V2</span>
  <span style="display:flex;gap:16px;align-items:center;">
    {hstatus('price_feed')}
    {hstatus('news_feed')}
    {hstatus('sentiment_feed')}
    {hstatus('onchain_feed')}
    {hstatus('trading')}
    <span style="color:#2b3139">|</span>
    <span>刷新: {now_str}</span>
  </span>
</div>
""", unsafe_allow_html=True)

# ─── 价格行 ────────────────────────────────────────────────────────────────────
price_items_html = ""
for sym in symbols:
    row = db.query_latest_price(conn, sym)
    if row:
        p   = row["price"]
        chg = row["change_24h"] or 0
        icon = "▲" if chg >= 0 else "▼"
        cls  = "pi-up" if chg >= 0 else "pi-dn"
        price_items_html += f"""
        <div class="price-item">
          <div class="pi-sym">{sym} / USDT</div>
          <div class="pi-price">${p:,.2f}</div>
          <div class="{cls}">{icon} {abs(chg):.2f}%</div>
        </div>"""
    else:
        price_items_html += f"""
        <div class="price-item">
          <div class="pi-sym">{sym} / USDT</div>
          <div class="pi-price" style="color:#848e9c">采集中...</div>
        </div>"""

st.markdown(f'<div class="price-bar">{price_items_html}</div>', unsafe_allow_html=True)

# ─── 主体：三列布局 ────────────────────────────────────────────────────────────
col_strat, col_exec, col_sent = st.columns([1, 1, 1])

# ── 策略状态 ──────────────────────────────────────────────────────────────────
with col_strat:
    st.markdown('<div class="card"><div class="card-title">⚡ 策略状态</div>', unsafe_allow_html=True)
    trading_health = health_map.get("trading")
    if trading_health:
        msg = trading_health.get("message", "")
        ts  = (trading_health.get("ts") or "")[:19]
        # 从 health message 提取关键字段
        def _extract(key, text):
            import re
            m = re.search(rf"{key}=([^\s]+)", text)
            return m.group(1) if m else "—"

        sig  = _extract("sig", msg)
        src  = _extract("src", msg)
        act  = _extract("act", msg)
        p    = _extract("p", msg)
        fg   = _extract("fg", msg)
        reg  = _extract("regime", msg)
        news = _extract("news", msg)
        cash = _extract("cash", msg)

        sig_cls = "sig-buy" if sig == "buy" else ("sig-sell" if sig == "sell" else "sig-hold")
        st.markdown(f"""
        <span class="{sig_cls}">{sig.upper()}</span>
        <div style="margin-top:10px;">
        <div class="kv-row"><span class="kv-label">来源</span><span class="kv-val">{src}</span></div>
        <div class="kv-row"><span class="kv-label">动作</span><span class="kv-val">{act}</span></div>
        <div class="kv-row"><span class="kv-label">价格</span><span class="kv-val">${p}</span></div>
        <div class="kv-row"><span class="kv-label">F&G</span><span class="kv-val">{fg}</span></div>
        <div class="kv-row"><span class="kv-label">Regime</span><span class="kv-val">{reg}</span></div>
        <div class="kv-row"><span class="kv-label">News</span><span class="kv-val">{news}</span></div>
        <div class="kv-row"><span class="kv-label">更新</span><span class="kv-val" style="font-size:.7rem">{ts}</span></div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown('<div style="color:#848e9c;font-size:.82rem;">Trading loop 尚未启动</div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# ── 执行状态 ──────────────────────────────────────────────────────────────────
with col_exec:
    st.markdown('<div class="card"><div class="card-title">📊 执行状态</div>', unsafe_allow_html=True)

    # 权益 & 持仓
    if equity_row:
        bal = equity_row["balance_usd"]
        pos = equity_row["position_usd"]
        eq  = equity_row["equity_usd"]
        pct = (pos / eq * 100) if eq else 0
        st.markdown(f"""
        <div class="kv-row"><span class="kv-label">现金</span>
          <span class="kv-val">${bal:,.2f}</span></div>
        <div class="kv-row"><span class="kv-label">持仓市值</span>
          <span class="kv-val">${pos:,.2f} ({pct:.1f}%)</span></div>
        <div class="kv-row"><span class="kv-label">总权益</span>
          <span class="kv-val">${eq:,.2f}</span></div>
        """, unsafe_allow_html=True)
    else:
        st.markdown('<div style="color:#848e9c;font-size:.82rem;">尚无权益记录</div>', unsafe_allow_html=True)

    # 最近成交
    if orders:
        st.markdown('<div style="margin-top:10px;font-size:.7rem;color:#848e9c;letter-spacing:.5px;">— 最近成交 —</div>', unsafe_allow_html=True)
        for o in orders:
            side_cls = "kv-up" if o["side"] == "buy" else "kv-dn"
            price_str = f"${float(o['fill_price']):,.2f}" if o["fill_price"] else "—"
            st.markdown(f"""
            <div class="kv-row">
              <span class="{side_cls}" style="min-width:32px">{o['side'].upper()}</span>
              <span class="kv-val">{o['symbol']} {float(o['qty']):.5f}</span>
              <span class="kv-val">{price_str}</span>
              <span style="color:#848e9c;font-size:.7rem">{(o['ts'] or '')[:16]}</span>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.markdown('<div style="margin-top:8px;color:#848e9c;font-size:.82rem;">尚无成交记录</div>', unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

# ── 消息面状态 ────────────────────────────────────────────────────────────────
with col_sent:
    st.markdown('<div class="card"><div class="card-title">🧭 消息面</div>', unsafe_allow_html=True)

    fg_val   = sent["fear_greed_value"] if sent else None
    news_sc  = sent["news_score"] if sent else None
    regime   = (sent["regime"] if sent else None) or "—"

    fg_color = "#f6465d" if fg_val and fg_val <= 25 else \
               "#f0b90b" if fg_val and fg_val <= 45 else \
               "#848e9c" if fg_val and fg_val <= 55 else \
               "#0ecb81" if fg_val and fg_val <= 75 else "#4cc9f0"
    fg_str   = f'<span style="color:{fg_color};font-weight:700">{fg_val}</span>' if fg_val else "N/A"

    if news_sc is not None:
        ns_color = "#0ecb81" if news_sc > 0.1 else ("#f6465d" if news_sc < -0.1 else "#848e9c")
        ns_str   = f'<span style="color:{ns_color};font-weight:700">{news_sc:+.3f}</span>'
    else:
        ns_str = '<span style="color:#848e9c">N/A</span>'

    comp_label, comp_cls, comp_icon = composite_sentiment(fg_val, news_sc)

    st.markdown(f"""
    <div class="kv-row"><span class="kv-label">Fear & Greed</span>
      <span class="kv-val">{fg_str}</span></div>
    <div class="kv-row"><span class="kv-label">Regime</span>
      <span class="kv-val">{regime}</span></div>
    <div class="kv-row"><span class="kv-label">News Score</span>
      <span class="kv-val">{ns_str}</span></div>
    <div class="kv-row"><span class="kv-label">综合情绪</span>
      <span class="{comp_cls}">{comp_icon} {comp_label}</span></div>
    """, unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

# ─── 最近新闻列表 ──────────────────────────────────────────────────────────────
st.markdown('<div class="card"><div class="card-title">📰 最近新闻情绪（最新10条）</div>', unsafe_allow_html=True)

if recent_news:
    news_html = ""
    for n in recent_news:
        sc = n["score"]
        if sc is None:
            sc_html = '<span class="news-score-neu">—</span>'
        elif sc > 0.05:
            sc_html = f'<span class="news-score-pos">{sc:+.2f}</span>'
        elif sc < -0.05:
            sc_html = f'<span class="news-score-neg">{sc:+.2f}</span>'
        else:
            sc_html = f'<span class="news-score-neu">{sc:+.2f}</span>'

        title   = (n["title"] or "")[:100]
        source  = n["source"] or "?"
        sym     = n["symbol"] or ""
        pub_at  = (n["published_at"] or "")[:16].replace("T", " ")
        url     = n["url"] or "#"

        news_html += f"""
        <div class="news-row">
          {sc_html}
          <div>
            <div class="news-title">
              <a href="{url}" target="_blank" style="color:#eaecef;text-decoration:none;"
                 onmouseover="this.style.color='#f0b90b'" onmouseout="this.style.color='#eaecef'">
                {title}
              </a>
            </div>
            <div class="news-meta">{sym} · {source} · {pub_at}</div>
          </div>
        </div>"""
    st.markdown(news_html, unsafe_allow_html=True)
else:
    st.markdown('<div style="color:#848e9c;font-size:.82rem;padding:8px 0;">尚无新闻数据（news_feed 可能正在初次采集）</div>', unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True)

# ─── 链上大额事件 ──────────────────────────────────────────────────────────────
st.markdown('<div class="card"><div class="card-title">🐳 链上大额事件</div>', unsafe_allow_html=True)

col_f, _ = st.columns([1, 4])
with col_f:
    min_eth = st.slider("最小筛选 ETH", 0, 5000, 100, 50, key="min_eth_slider")

events = db.query_onchain_events(conn, limit=20, min_eth=min_eth)
if events:
    rows_disp = [{
        "时间 (UTC)": e["ts"][:19],
        "金额 (ETH)": f"{e['amount_eth']:,.2f}",
        "美元价值":   f"${e['usd_value']:,.0f}" if e["usd_value"] else "N/A",
        "发送方":     get_tag(e["from_addr"]),
        "接收方":     get_tag(e["to_addr"]),
        "区块":       f"{e['block_no']:,}" if e["block_no"] else "—",
        "链接":       f"https://etherscan.io/tx/{e['tx_hash']}",
    } for e in events]
    st.dataframe(
        pd.DataFrame(rows_disp),
        use_container_width=True,
        hide_index=True,
        column_config={
            "链接": st.column_config.LinkColumn("Etherscan 🔗", display_text="查看 ↗")
        },
    )
else:
    st.caption(f"暂无 ≥ {min_eth} ETH 的链上事件")

st.markdown("</div>", unsafe_allow_html=True)

# ─── 自动刷新（30s）──────────────────────────────────────────────────────────
st.markdown(
    "<script>setTimeout(()=>window.location.reload(),30000);</script>",
    unsafe_allow_html=True,
)
