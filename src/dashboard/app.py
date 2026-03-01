"""
src/dashboard/app.py — CryptoProject · Execution Console / 执行控制台

支持中文 / English 界面切换（右上角按钮）。
布局：顶栏 → 价格行 → 策略/执行/消息面 → 新闻列表 → 链上事件
"""

import re
import sys
import yaml
import pandas as pd
import streamlit as st
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from src.storage import db

# ─── 翻译字典 ──────────────────────────────────────────────────────────────────
LANGS: dict[str, dict] = {
    "中文": {
        "page_title":      "加密执行控制台",
        "brand":           "⚡ 加密执行控制台 V2",
        "refresh_label":   "刷新",
        "loading":         "采集中...",
        "lang_btn":        "EN",
        # 卡片标题
        "card_strategy":   "⚡ 策略状态",
        "card_exec":       "📊 执行状态",
        "card_sentiment":  "🧭 消息面",
        "card_news":       "📰 最近新闻情绪（最新10条）",
        "card_whale":      "🐳 链上大额事件",
        # 策略面板标签
        "lbl_source":      "来源",
        "lbl_action":      "动作",
        "lbl_price":       "价格",
        "lbl_fg":          "恐贪指数",
        "lbl_regime":      "市场态势",
        "lbl_news_score":  "新闻分",
        "lbl_updated":     "更新时间",
        # 执行面板标签
        "lbl_cash":        "现金",
        "lbl_pos":         "持仓市值",
        "lbl_equity":      "总权益",
        "lbl_recent":      "— 最近成交 —",
        # 情绪面板标签
        "lbl_composite":   "综合情绪",
        # 空状态文案
        "empty_trading":   "Trading loop 尚未启动",
        "empty_equity":    "尚无权益记录",
        "empty_orders":    "尚无成交记录",
        "empty_news":      "尚无新闻数据（news_feed 可能正在初次采集）",
        "empty_whale":     "暂无",
        # 链上事件
        "eth_filter":      "最小筛选 ETH",
        "col_time":        "时间 (UTC)",
        "col_eth":         "金额 (ETH)",
        "col_usd":         "美元价值",
        "col_from":        "发送方",
        "col_to":          "接收方",
        "col_block":       "区块",
        "col_link":        "Etherscan 🔗",
        "link_text":       "查看 ↗",
        # 综合情绪标签
        "bullish":         "↑ 看多",
        "bearish":         "↓ 看空",
        "neutral_bull":    "→ 中性/偏多",
        "neutral_bear":    "→ 中性/偏空",
        "neutral":         "— 中性",
    },
    "EN": {
        "page_title":      "Crypto Exec Console",
        "brand":           "⚡ CRYPTO EXEC CONSOLE V2",
        "refresh_label":   "Refreshed",
        "loading":         "Loading...",
        "lang_btn":        "中文",
        # card titles
        "card_strategy":   "⚡ Strategy",
        "card_exec":       "📊 Execution",
        "card_sentiment":  "🧭 Sentiment",
        "card_news":       "📰 Latest News Sentiment (Top 10)",
        "card_whale":      "🐳 On-Chain Whale Events",
        # strategy panel
        "lbl_source":      "Source",
        "lbl_action":      "Action",
        "lbl_price":       "Price",
        "lbl_fg":          "Fear & Greed",
        "lbl_regime":      "Regime",
        "lbl_news_score":  "News Score",
        "lbl_updated":     "Updated",
        # execution panel
        "lbl_cash":        "Cash",
        "lbl_pos":         "Position Value",
        "lbl_equity":      "Total Equity",
        "lbl_recent":      "— Recent Trades —",
        # sentiment panel
        "lbl_composite":   "Composite",
        # empty states
        "empty_trading":   "Trading loop not started yet",
        "empty_equity":    "No equity records yet",
        "empty_orders":    "No fills yet",
        "empty_news":      "No news data yet (news_feed may be on first run)",
        "empty_whale":     "None",
        # whale events
        "eth_filter":      "Min ETH Filter",
        "col_time":        "Time (UTC)",
        "col_eth":         "Amount (ETH)",
        "col_usd":         "USD Value",
        "col_from":        "From",
        "col_to":          "To",
        "col_block":       "Block",
        "col_link":        "Etherscan 🔗",
        "link_text":       "View ↗",
        # composite sentiment labels
        "bullish":         "↑ Bullish",
        "bearish":         "↓ Bearish",
        "neutral_bull":    "→ Neutral / Bullish",
        "neutral_bear":    "→ Neutral / Bearish",
        "neutral":         "— Neutral",
    },
}

# ─── 语言状态（session_state 跨刷新保持）──────────────────────────────────────
if "lang" not in st.session_state:
    st.session_state["lang"] = "中文"

# ─── 页面配置（必须在任何 st. 调用之前）──────────────────────────────────────
T = LANGS[st.session_state["lang"]]

st.set_page_config(
    page_title=T["page_title"],
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
html, body, .stApp { background:#0b0e11 !important; color:#eaecef; }
[data-testid="stSidebar"]    { background:#131722; }
[data-testid="stHeader"]     { display:none !important; }
[data-testid="stToolbar"]    { display:none !important; }
[data-testid="stDecoration"] { display:none !important; }
#MainMenu { display:none !important; }
footer    { display:none !important; }

.block-container {
    padding-top: 4px !important;
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

/* 语言切换按钮覆盖 */
div[data-testid="stButton"] button {
    background:#1e2329 !important; color:#f0b90b !important;
    border:1px solid #f0b90b !important; border-radius:4px !important;
    padding:2px 10px !important; font-size:.75rem !important;
    font-weight:600 !important; height:28px !important;
}
div[data-testid="stButton"] button:hover {
    background:#f0b90b !important; color:#0b0e11 !important;
}

/* 价格条 */
.price-bar {
    display:flex; gap:0; background:#131722;
    border:1px solid #1e2329; border-radius:6px;
    padding:0; margin-bottom:16px; overflow:hidden;
}
.price-item { flex:1; padding:10px 16px; border-right:1px solid #1e2329; }
.price-item:last-child { border-right:none; }
.pi-sym   { font-size:.7rem; color:#848e9c; font-weight:600; letter-spacing:.5px; }
.pi-price { font-size:1.15rem; font-weight:700; color:#eaecef; margin:2px 0; }
.pi-up    { color:#0ecb81; font-size:.8rem; font-weight:600; }
.pi-dn    { color:#f6465d; font-size:.8rem; font-weight:600; }

/* 卡片 */
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

/* 键值行 */
.kv-row  { display:flex; justify-content:space-between;
           padding:4px 0; border-bottom:1px solid #1e2329; font-size:.82rem; }
.kv-row:last-child { border-bottom:none; }
.kv-label { color:#848e9c; }
.kv-val   { color:#eaecef; font-weight:600; }
.kv-up    { color:#0ecb81; font-weight:600; }
.kv-dn    { color:#f6465d; font-weight:600; }

/* 综合情绪 */
.composite-bull { font-size:1.1rem; font-weight:700; color:#0ecb81; }
.composite-bear { font-size:1.1rem; font-weight:700; color:#f6465d; }
.composite-neu  { font-size:1.1rem; font-weight:700; color:#848e9c; }

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

[data-testid="stDataFrame"] { border-radius:4px; }
</style>
""", unsafe_allow_html=True)

# ─── 语言切换按钮（顶部右侧，在 topbar HTML 之前渲染）──────────────────────
_spacer, _lang_col = st.columns([11, 1])
with _lang_col:
    if st.button(T["lang_btn"], key="lang_toggle"):
        st.session_state["lang"] = "EN" if st.session_state["lang"] == "中文" else "中文"
        st.rerun()

# 切换后重新绑定翻译
T = LANGS[st.session_state["lang"]]

# ─── 资源加载 ─────────────────────────────────────────────────────────────────
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

# ─── 综合情绪判断 ─────────────────────────────────────────────────────────────
def composite_sentiment(fg_value, news_score):
    fg_bull   = fg_value is not None and fg_value > 55
    fg_bear   = fg_value is not None and fg_value < 45
    news_bull = news_score is not None and news_score > 0.1
    news_bear = news_score is not None and news_score < -0.1
    bull = sum([fg_bull, news_bull])
    bear = sum([fg_bear, news_bear])
    if bull >= 2:
        return T["bullish"],      "composite-bull"
    if bear >= 2:
        return T["bearish"],      "composite-bear"
    if bull > bear:
        return T["neutral_bull"], "composite-neu"
    if bear > bull:
        return T["neutral_bear"], "composite-neu"
    return T["neutral"],          "composite-neu"

# ─── 从 health message 提取 key=value ────────────────────────────────────────
def _extract(key, text):
    m = re.search(rf"{key}=([^\s]+)", text)
    return m.group(1) if m else "—"

# ─── 数据查询 ─────────────────────────────────────────────────────────────────
health      = db.query_latest_health(conn)
health_map  = {r["module"]: r for r in health}
sent        = db.query_latest_sentiment(conn)
equity_row  = db.query_latest_equity(conn)
recent_news = db.query_news_events(conn, limit=10)
orders      = db.query_recent_orders(conn, limit=5)

# ─── 顶部状态栏 ───────────────────────────────────────────────────────────────
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
  <span class="brand">{T['brand']}</span>
  <span style="display:flex;gap:16px;align-items:center;">
    {hstatus('price_feed')}
    {hstatus('news_feed')}
    {hstatus('sentiment_feed')}
    {hstatus('onchain_feed')}
    {hstatus('trading')}
    <span style="color:#2b3139">|</span>
    <span>{T['refresh_label']}: {now_str}</span>
  </span>
</div>
""", unsafe_allow_html=True)

# ─── 价格行 ───────────────────────────────────────────────────────────────────
price_html = ""
for sym in symbols:
    row = db.query_latest_price(conn, sym)
    if row:
        p   = row["price"]
        chg = row["change_24h"] or 0
        icon = "▲" if chg >= 0 else "▼"
        cls  = "pi-up" if chg >= 0 else "pi-dn"
        price_html += f"""
        <div class="price-item">
          <div class="pi-sym">{sym} / USDT</div>
          <div class="pi-price">${p:,.2f}</div>
          <div class="{cls}">{icon} {abs(chg):.2f}%</div>
        </div>"""
    else:
        price_html += f"""
        <div class="price-item">
          <div class="pi-sym">{sym} / USDT</div>
          <div class="pi-price" style="color:#848e9c">{T['loading']}</div>
        </div>"""

st.markdown(f'<div class="price-bar">{price_html}</div>', unsafe_allow_html=True)

# ─── 三列主体 ─────────────────────────────────────────────────────────────────
col_strat, col_exec, col_sent = st.columns([1, 1, 1])

# ── 策略状态 ──────────────────────────────────────────────────────────────────
with col_strat:
    st.markdown(f'<div class="card"><div class="card-title">{T["card_strategy"]}</div>', unsafe_allow_html=True)
    th = health_map.get("trading")
    if th:
        msg = th["message"] or ""
        ts  = (th["ts"] or "")[:19]
        sig  = _extract("sig",    msg)
        src  = _extract("src",    msg)
        act  = _extract("act",    msg)
        p    = _extract("p",      msg)
        fg   = _extract("fg",     msg)
        reg  = _extract("regime", msg)
        news = _extract("news",   msg)

        sig_cls = "sig-buy" if sig == "buy" else ("sig-sell" if sig == "sell" else "sig-hold")
        st.markdown(f"""
        <span class="{sig_cls}">{sig.upper()}</span>
        <div style="margin-top:10px;">
        <div class="kv-row"><span class="kv-label">{T['lbl_source']}</span><span class="kv-val">{src}</span></div>
        <div class="kv-row"><span class="kv-label">{T['lbl_action']}</span><span class="kv-val">{act}</span></div>
        <div class="kv-row"><span class="kv-label">{T['lbl_price']}</span><span class="kv-val">${p}</span></div>
        <div class="kv-row"><span class="kv-label">{T['lbl_fg']}</span><span class="kv-val">{fg}</span></div>
        <div class="kv-row"><span class="kv-label">{T['lbl_regime']}</span><span class="kv-val">{reg}</span></div>
        <div class="kv-row"><span class="kv-label">{T['lbl_news_score']}</span><span class="kv-val">{news}</span></div>
        <div class="kv-row"><span class="kv-label">{T['lbl_updated']}</span>
          <span class="kv-val" style="font-size:.7rem">{ts}</span></div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f'<div style="color:#848e9c;font-size:.82rem;">{T["empty_trading"]}</div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# ── 执行状态 ──────────────────────────────────────────────────────────────────
with col_exec:
    st.markdown(f'<div class="card"><div class="card-title">{T["card_exec"]}</div>', unsafe_allow_html=True)

    if equity_row:
        bal = equity_row["balance_usd"]
        pos = equity_row["position_usd"]
        eq  = equity_row["equity_usd"]
        pct = (pos / eq * 100) if eq else 0
        st.markdown(f"""
        <div class="kv-row"><span class="kv-label">{T['lbl_cash']}</span>
          <span class="kv-val">${bal:,.2f}</span></div>
        <div class="kv-row"><span class="kv-label">{T['lbl_pos']}</span>
          <span class="kv-val">${pos:,.2f} ({pct:.1f}%)</span></div>
        <div class="kv-row"><span class="kv-label">{T['lbl_equity']}</span>
          <span class="kv-val">${eq:,.2f}</span></div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f'<div style="color:#848e9c;font-size:.82rem;">{T["empty_equity"]}</div>', unsafe_allow_html=True)

    if orders:
        st.markdown(f'<div style="margin-top:10px;font-size:.7rem;color:#848e9c;letter-spacing:.5px;">{T["lbl_recent"]}</div>', unsafe_allow_html=True)
        for o in orders:
            side_cls  = "kv-up" if o["side"] == "buy" else "kv-dn"
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
        st.markdown(f'<div style="margin-top:8px;color:#848e9c;font-size:.82rem;">{T["empty_orders"]}</div>', unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

# ── 消息面 ────────────────────────────────────────────────────────────────────
with col_sent:
    st.markdown(f'<div class="card"><div class="card-title">{T["card_sentiment"]}</div>', unsafe_allow_html=True)

    fg_val  = sent["fear_greed_value"] if sent else None
    news_sc = sent["news_score"]       if sent else None
    regime  = (sent["regime"]          if sent else None) or "—"

    fg_color = ("#f6465d" if fg_val and fg_val <= 25 else
                "#f0b90b" if fg_val and fg_val <= 45 else
                "#848e9c" if fg_val and fg_val <= 55 else
                "#0ecb81" if fg_val and fg_val <= 75 else "#4cc9f0")
    fg_str  = f'<span style="color:{fg_color};font-weight:700">{fg_val}</span>' if fg_val else "N/A"

    if news_sc is not None:
        ns_color = "#0ecb81" if news_sc > 0.1 else ("#f6465d" if news_sc < -0.1 else "#848e9c")
        ns_str   = f'<span style="color:{ns_color};font-weight:700">{news_sc:+.3f}</span>'
    else:
        ns_str = '<span style="color:#848e9c">N/A</span>'

    comp_label, comp_cls = composite_sentiment(fg_val, news_sc)

    st.markdown(f"""
    <div class="kv-row"><span class="kv-label">{T['lbl_fg']}</span>
      <span class="kv-val">{fg_str}</span></div>
    <div class="kv-row"><span class="kv-label">{T['lbl_regime']}</span>
      <span class="kv-val">{regime}</span></div>
    <div class="kv-row"><span class="kv-label">{T['lbl_news_score']}</span>
      <span class="kv-val">{ns_str}</span></div>
    <div class="kv-row"><span class="kv-label">{T['lbl_composite']}</span>
      <span class="{comp_cls}">{comp_label}</span></div>
    """, unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

# ─── 新闻列表 ─────────────────────────────────────────────────────────────────
st.markdown(f'<div class="card"><div class="card-title">{T["card_news"]}</div>', unsafe_allow_html=True)

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

        title  = (n["title"]        or "")[:100]
        source = n["source"]        or "?"
        sym    = n["symbol"]        or ""
        pub_at = (n["published_at"] or "")[:16].replace("T", " ")
        url    = n["url"]           or "#"

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
    st.markdown(f'<div style="color:#848e9c;font-size:.82rem;padding:8px 0;">{T["empty_news"]}</div>', unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True)

# ─── 链上大额事件 ─────────────────────────────────────────────────────────────
st.markdown(f'<div class="card"><div class="card-title">{T["card_whale"]}</div>', unsafe_allow_html=True)

col_f, _ = st.columns([1, 4])
with col_f:
    min_eth = st.slider(T["eth_filter"], 0, 5000, 100, 50, key="min_eth_slider")

events = db.query_onchain_events(conn, limit=20, min_eth=min_eth)
if events:
    rows_disp = [{
        T["col_time"]:  e["ts"][:19],
        T["col_eth"]:   f"{e['amount_eth']:,.2f}",
        T["col_usd"]:   f"${e['usd_value']:,.0f}" if e["usd_value"] else "N/A",
        T["col_from"]:  get_tag(e["from_addr"]),
        T["col_to"]:    get_tag(e["to_addr"]),
        T["col_block"]: f"{e['block_no']:,}" if e["block_no"] else "—",
        T["col_link"]:  f"https://etherscan.io/tx/{e['tx_hash']}",
    } for e in events]
    st.dataframe(
        pd.DataFrame(rows_disp),
        use_container_width=True,
        hide_index=True,
        column_config={
            T["col_link"]: st.column_config.LinkColumn(T["col_link"], display_text=T["link_text"])
        },
    )
else:
    st.caption(f"{T['empty_whale']} ≥ {min_eth} ETH")

st.markdown("</div>", unsafe_allow_html=True)

# ─── 自动刷新 30s ─────────────────────────────────────────────────────────────
st.markdown(
    "<script>setTimeout(()=>window.location.reload(),30000);</script>",
    unsafe_allow_html=True,
)
