"""
src/dashboard/app.py — CryptoProject V1 · 交易终端风看板

布局：仿交易所终端
  - 顶栏：系统状态 + 最后更新
  - 主区：[币种Tab] → [图表头：价格/涨跌/Vol/F&G + 周期选择 + 指标选择] → [全宽K线]
  - 底区：链上鲸鱼事件表

数据源：CoinGecko market_chart（15m/30m/1h）· CoinGecko OHLC（4h/1D/1W）
指标：布林带 BB(20) · MA7/MA25 · RSI(14)
"""

import sys, yaml, requests
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from src.storage import db

# ─── 页面配置 ─────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CryptoProject V1",
    page_icon="🐳",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── CSS：交易终端风 ──────────────────────────────────────────────────────────
st.markdown("""
<style>
/* 全局背景 */
html, body, .stApp { background:#0b0e11 !important; color:#eaecef; }
[data-testid="stSidebar"] { background:#131722; }

/* ① 隐藏 Streamlit 自带的顶部 header（约 58px），释放页顶空间 */
[data-testid="stHeader"]        { display:none !important; }
[data-testid="stToolbar"]       { display:none !important; }
[data-testid="stDecoration"]    { display:none !important; }
#MainMenu                        { display:none !important; }
footer                           { display:none !important; }

/* ② block-container：顶部 8px 留白即可，底部 80px 确保末尾内容不被浏览器 UI 遮住 */
.block-container {
    padding-top:    8px  !important;
    padding-bottom: 80px !important;
    max-width:      100% !important;
}

/* 顶部状态栏 */
.topbar {
    display:flex; justify-content:space-between; align-items:center;
    background:#131722; border-bottom:1px solid #1e2329;
    padding:6px 20px; font-size:.78rem; color:#848e9c;
    margin-bottom:0;
}
.topbar .brand { color:#f0b90b; font-weight:700; font-size:.9rem; letter-spacing:1px; }
.topbar .status-ok  { color:#0ecb81; }
.topbar .status-err { color:#f6465d; }

/* 图表头信息行 */
.chart-header {
    background:#131722; border:1px solid #1e2329; border-bottom:none;
    border-radius:6px 6px 0 0; padding:10px 16px;
    display:flex; align-items:center; gap:24px; flex-wrap:wrap;
}
.ch-price  { font-size:1.55rem; font-weight:700; color:#eaecef; }
.ch-up     { color:#0ecb81; font-size:.92rem; font-weight:600; }
.ch-dn     { color:#f6465d; font-size:.92rem; font-weight:600; }
.ch-label  { font-size:.7rem; color:#848e9c; margin-bottom:1px; }
.ch-val    { font-size:.88rem; color:#eaecef; }
.ch-divider{ width:1px; height:32px; background:#1e2329; }

/* K线容器 */
.chart-wrap {
    background:#131722; border:1px solid #1e2329;
    border-top:none; border-radius:0 0 6px 6px;
    padding:0; margin-bottom:16px;
}

/* 控制栏（周期 + 指标）*/
.ctrl-row {
    background:#1e2329; border-radius:4px;
    padding:6px 12px; margin-bottom:8px;
    display:flex; align-items:center; gap:12px;
}

/* 鲸鱼事件表 */
.whale-section {
    background:#131722; border:1px solid #1e2329;
    border-radius:6px; padding:12px 16px;
}
.sec-title {
    font-size:.75rem; font-weight:600; color:#848e9c;
    text-transform:uppercase; letter-spacing:1.2px;
    margin-bottom:10px;
}

/* Streamlit 覆盖 */
div[data-testid="stTabs"] button {
    background:#1e2329 !important; color:#848e9c !important;
    border:none !important; border-radius:4px 4px 0 0 !important;
    font-size:.82rem !important; padding:6px 16px !important;
}
div[data-testid="stTabs"] button[aria-selected="true"] {
    color:#f0b90b !important; border-bottom:2px solid #f0b90b !important;
    background:#131722 !important;
}
/* radio 横排 */
div[data-testid="stRadio"] > div { flex-direction:row; gap:4px; }
div[data-testid="stRadio"] label {
    background:#1e2329; color:#848e9c; border-radius:4px;
    padding:3px 10px; font-size:.78rem; cursor:pointer;
    border:1px solid #2b3139;
}
div[data-testid="stRadio"] label:has(input:checked) {
    background:#2b3139; color:#f0b90b; border-color:#f0b90b;
}
/* multiselect */
div[data-testid="stMultiSelect"] > div > div {
    background:#1e2329 !important; border-color:#2b3139 !important;
    font-size:.8rem !important;
}
/* dataframe */
[data-testid="stDataFrame"] { border-radius:4px; }
/* (已在顶部统一隐藏 Streamlit chrome) */
</style>
""", unsafe_allow_html=True)

# ─── 资源 ─────────────────────────────────────────────────────────────────────
@st.cache_resource
def load_resources():
    cfg = PROJECT_ROOT / "configs" / "settings.yaml"
    with open(cfg, "r", encoding="utf-8") as f:
        settings = yaml.safe_load(f)
    conn = db.get_connection(settings["database"]["path"])
    db.init_tables(conn)
    return settings, conn

settings, conn = load_resources()
address_tags = settings.get("address_tags", {})
symbols = settings["price_feed"]["symbols"]
CG_IDS  = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "BNB": "binancecoin"}

def get_tag(addr):
    if not addr: return "Unknown"
    return address_tags.get(addr.lower(), f"{addr[:8]}...{addr[-6:]}")

# ─── 时间粒度 ─────────────────────────────────────────────────────────────────
TIMEFRAMES = {
    "15m": {"source": "cg_chart", "days": 1, "resample": "15min", "label": "近24h"},
    "30m": {"source": "cg_chart", "days": 1, "resample": "30min", "label": "近24h"},
    "1h":  {"source": "cg_chart", "days": 1, "resample": "1h",   "label": "近24h"},
    "4h":  {"source": "cg",       "days": 7,                     "label": "近7天"},
    "1D":  {"source": "cg",       "days": 90,                    "label": "近3月"},
    "1W":  {"source": "cg",       "days": "max",                 "label": "全史"},
}

# ─── 数据获取 ─────────────────────────────────────────────────────────────────
@st.cache_data(ttl=120)
def fetch_ohlc_cg(cg_id, days):
    try:
        r = requests.get(
            f"https://api.coingecko.com/api/v3/coins/{cg_id}/ohlc",
            params={"vs_currency": "usd", "days": str(days)}, timeout=15)
        r.raise_for_status()
        df = pd.DataFrame(r.json(), columns=["ts","open","high","low","close"])
        df["ts"] = pd.to_datetime(df["ts"], unit="ms")
        return df
    except: return pd.DataFrame()

@st.cache_data(ttl=120)
def fetch_market_chart_ohlc(cg_id, days, resample):
    try:
        r = requests.get(
            f"https://api.coingecko.com/api/v3/coins/{cg_id}/market_chart",
            params={"vs_currency": "usd", "days": str(days)}, timeout=15)
        r.raise_for_status()
        prices = r.json()["prices"]
        df = pd.DataFrame(prices, columns=["ts","price"])
        df["ts"] = pd.to_datetime(df["ts"], unit="ms")
        ohlc = df.set_index("ts")["price"].resample(resample).ohlc().dropna()
        ohlc.index.name = "ts"
        result = ohlc.reset_index()
        result.columns = ["ts","open","high","low","close"]
        return result
    except: return pd.DataFrame()

def get_ohlc(symbol, tf_key):
    cfg   = TIMEFRAMES[tf_key]
    cg_id = CG_IDS.get(symbol, "bitcoin")
    if cfg["source"] == "cg_chart":
        return fetch_market_chart_ohlc(cg_id, cfg["days"], cfg["resample"])
    return fetch_ohlc_cg(cg_id, cfg["days"])

@st.cache_data(ttl=300)
def fetch_fear_greed():
    try:
        d = requests.get("https://api.alternative.me/fng/", timeout=8).json()["data"][0]
        return {"value": int(d["value"]), "label": d["value_classification"]}
    except: return {"value": None, "label": "N/A"}

# ─── 技术指标 ─────────────────────────────────────────────────────────────────
def calc_bb(df, period=20, std=2):
    df = df.copy()
    df["bb_mid"]   = df["close"].rolling(period).mean()
    df["bb_std"]   = df["close"].rolling(period).std()
    df["bb_upper"] = df["bb_mid"] + std * df["bb_std"]
    df["bb_lower"] = df["bb_mid"] - std * df["bb_std"]
    return df

def calc_ma(df, periods=(7, 25)):
    df = df.copy()
    for p in periods:
        df[f"ma{p}"] = df["close"].rolling(p).mean()
    return df

def calc_rsi(df, period=14):
    df    = df.copy()
    delta = df["close"].diff()
    gain  = delta.clip(lower=0).ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    loss  = (-delta).clip(lower=0).ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    df["rsi"] = 100 - 100 / (1 + gain / (loss + 1e-10))
    return df

# ─── 图表绘制 ─────────────────────────────────────────────────────────────────
DARK = dict(
    paper_bgcolor="#131722", plot_bgcolor="#0b0e11",
    font=dict(color="#848e9c", size=11),
    legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h",
                yanchor="bottom", y=1.01, xanchor="left", x=0, font_size=11),
    margin=dict(l=0, r=0, t=8, b=0),
    xaxis=dict(showgrid=False, color="#848e9c", rangeslider_visible=False,
               showline=False, zeroline=False),
    yaxis=dict(showgrid=True, gridcolor="#1e2329", color="#848e9c",
               showline=False, zeroline=False, side="right"),
)

def make_chart(df, symbol, indicators):
    has_rsi  = "RSI (14)" in indicators
    row_h    = [0.7, 0.3] if has_rsi else [1.0]
    height   = 680 if has_rsi else 560

    fig = make_subplots(
        rows=2 if has_rsi else 1, cols=1,
        shared_xaxes=True, vertical_spacing=0.02,
        row_heights=row_h,
    )

    # K线主体
    fig.add_trace(go.Candlestick(
        x=df["ts"], open=df["open"], high=df["high"],
        low=df["low"], close=df["close"],
        increasing=dict(line=dict(color="#0ecb81", width=1), fillcolor="#0ecb81"),
        decreasing=dict(line=dict(color="#f6465d", width=1), fillcolor="#f6465d"),
        name=symbol, showlegend=False,
        whiskerwidth=0,
    ), row=1, col=1)

    # 布林带
    if "布林带 BB(20)" in indicators and len(df) >= 20:
        df = calc_bb(df)
        kw = dict(mode="lines", showlegend=True)
        fig.add_trace(go.Scatter(x=df["ts"], y=df["bb_upper"],
            name="BB上轨", line=dict(color="#f0b90b", width=1, dash="dot"), **kw), row=1, col=1)
        fig.add_trace(go.Scatter(x=df["ts"], y=df["bb_mid"],
            name="BB中轨", line=dict(color="#848e9c", width=1), **kw), row=1, col=1)
        fig.add_trace(go.Scatter(x=df["ts"], y=df["bb_lower"],
            name="BB下轨", line=dict(color="#f0b90b", width=1, dash="dot"),
            fill="tonexty", fillcolor="rgba(240,185,11,0.05)", **kw), row=1, col=1)

    # 均线
    if "均线 MA7/MA25" in indicators:
        df = calc_ma(df)
        if "ma7" in df.columns:
            fig.add_trace(go.Scatter(x=df["ts"], y=df["ma7"],
                name="MA7", line=dict(color="#c77dff", width=1.5),
                mode="lines", showlegend=True), row=1, col=1)
        if "ma25" in df.columns:
            fig.add_trace(go.Scatter(x=df["ts"], y=df["ma25"],
                name="MA25", line=dict(color="#4cc9f0", width=1.5),
                mode="lines", showlegend=True), row=1, col=1)

    # RSI 副图
    if has_rsi and len(df) >= 14:
        df = calc_rsi(df)
        fig.add_trace(go.Scatter(x=df["ts"], y=df["rsi"],
            name="RSI(14)", line=dict(color="#f0b90b", width=1.5),
            mode="lines", showlegend=True), row=2, col=1)
        for lvl, col, dash in [(70,"#f6465d","dash"),(30,"#0ecb81","dash"),(50,"#2b3139","dot")]:
            fig.add_hline(y=lvl, line_dash=dash, line_color=col,
                          line_width=1, opacity=0.8, row=2, col=1)
        fig.update_yaxes(range=[0,100], showgrid=True, gridcolor="#1e2329",
                         color="#848e9c", side="right", row=2, col=1)

    fig.update_layout(**DARK, height=height)
    # 统一 x 轴样式
    fig.update_xaxes(showgrid=False, color="#848e9c",
                     rangeslider_visible=False, showline=False)
    return fig

# ═══════════════════════════════════════════════════════════════════════════════
# 渲染
# ═══════════════════════════════════════════════════════════════════════════════

# ── 顶部状态栏 ────────────────────────────────────────────────────────────────
health = db.query_latest_health(conn)
health_map = {r["module"]: r for r in health}
def hstatus(module):
    r = health_map.get(module)
    if not r: return "<span class='status-err'>离线</span>"
    cls = "status-ok" if r["status"] == "ok" else "status-err"
    return f"<span class='{cls}'>{'●' if r['status']=='ok' else '✕'} {module}</span>"

now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
st.markdown(f"""
<div class="topbar">
  <span class="brand">🐳 CRYPTO MONITOR V1</span>
  <span style="display:flex;gap:16px;align-items:center;">
    {hstatus('price_feed')}
    {hstatus('onchain_feed')}
    {hstatus('sentiment_feed')}
    <span style="color:#2b3139">|</span>
    <span>刷新: {now_str}</span>
  </span>
</div>
""", unsafe_allow_html=True)

sent = db.query_latest_sentiment(conn)
c1, c2, c3 = st.columns(3)
with c1:
    st.metric("Fear & Greed", sent["fear_greed_value"] if sent and sent["fear_greed_value"] is not None else "N/A")
with c2:
    st.metric("Regime", sent["regime"] if sent and sent["regime"] else "unknown")
with c3:
    st.metric("News Score", sent["news_score"] if sent and sent["news_score"] is not None else "N/A")

# ── 主体：币种 Tab ─────────────────────────────────────────────────────────────
tabs = st.tabs([f"  {s}  " for s in symbols])

fg = fetch_fear_greed()

for i, sym in enumerate(symbols):
    with tabs[i]:

        # 从 DB 拿最新价格数据
        row     = db.query_latest_price(conn, sym)
        price   = row["price"]      if row else None
        chg     = row["change_24h"] if row else None
        vol     = row["volume_24h"] if row else None

        # ── 控制栏（周期 + 指标）─────────────────────────────────────────────
        ctrl_l, ctrl_r = st.columns([2, 3])
        with ctrl_l:
            tf_key = st.radio(
                "周期", list(TIMEFRAMES.keys()),
                horizontal=True, label_visibility="collapsed",
                key=f"tf_{sym}",
            )
        with ctrl_r:
            indicators = st.multiselect(
                "指标", ["布林带 BB(20)", "均线 MA7/MA25", "RSI (14)"],
                default=[], placeholder="叠加指标（可多选）...",
                label_visibility="collapsed",
                key=f"ind_{sym}",
            )

        # ── 图表头信息行 ──────────────────────────────────────────────────────
        if price:
            chg_cls  = "ch-up" if (chg or 0) >= 0 else "ch-dn"
            chg_icon = "▲" if (chg or 0) >= 0 else "▼"
            vol_str  = f"${vol/1e9:.2f}B" if vol else "—"
            fg_v     = fg["value"]
            fg_color = "#f6465d" if fg_v and fg_v<=25 else \
                       "#f0b90b" if fg_v and fg_v<=45 else \
                       "#eaecef" if fg_v and fg_v<=55 else \
                       "#0ecb81" if fg_v and fg_v<=75 else "#4cc9f0"
            fg_str   = f'{fg_v} <span style="color:{fg_color}">{fg["label"]}</span>' \
                       if fg_v else "N/A"

            st.markdown(f"""
            <div class="chart-header">
              <div>
                <div class="ch-label">{sym} / USDT</div>
                <div class="ch-price">${price:,.2f}</div>
              </div>
              <div class="ch-divider"></div>
              <div>
                <div class="ch-label">24h 涨跌</div>
                <div class="{chg_cls}">{chg_icon} {abs(chg or 0):.2f}%</div>
              </div>
              <div class="ch-divider"></div>
              <div>
                <div class="ch-label">24h 成交量</div>
                <div class="ch-val">{vol_str}</div>
              </div>
              <div class="ch-divider"></div>
              <div>
                <div class="ch-label">恐贪指数</div>
                <div class="ch-val">{fg_str}</div>
              </div>
              <div class="ch-divider"></div>
              <div>
                <div class="ch-label">周期 / 数据</div>
                <div class="ch-val">{tf_key} &nbsp;·&nbsp; {TIMEFRAMES[tf_key]['label']}</div>
              </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="chart-header"><div class="ch-label">{sym} 数据采集中...</div></div>',
                        unsafe_allow_html=True)

        # ── K线图（全宽）─────────────────────────────────────────────────────
        df_k = get_ohlc(sym, tf_key)
        if df_k.empty:
            st.info("K线数据获取失败，请稍后重试（CoinGecko 限速约 30s 一次）")
        else:
            n = len(df_k)
            # 数据不足时给出温馨提示
            short_warns = [name for name, need in
                           [("布林带 BB(20)", 20), ("均线 MA7/MA25", 7), ("RSI (14)", 14)]
                           if name in indicators and n < need]
            if short_warns:
                st.caption(f"⚠️ 当前 {n} 根蜡烛，{', '.join(short_warns)} 需要更多数据，已跳过")

            fig = make_chart(df_k, sym, indicators)
            st.plotly_chart(fig, use_container_width=True,
                            config={"displayModeBar": True,
                                    "modeBarButtonsToRemove": ["select2d","lasso2d","autoScale2d"],
                                    "displaylogo": False,
                                    "scrollZoom": True})

        st.markdown("---")

        # ── 链上鲸鱼事件（每个币种页都展示）────────────────────────────────
        c_filter, _ = st.columns([1, 4])
        with c_filter:
            min_eth = st.slider("最小筛选 ETH", 0, 5000, 100, 50, key=f"eth_{sym}")

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
                pd.DataFrame(rows_disp), use_container_width=True, hide_index=True,
                column_config={
                    "链接": st.column_config.LinkColumn("Etherscan 🔗", display_text="查看 ↗")
                }
            )
        else:
            st.caption(f"暂无 ≥ {min_eth} ETH 的链上事件")

# ─── 自动刷新 ─────────────────────────────────────────────────────────────────
st.markdown(
    "<script>setTimeout(()=>window.location.reload(),30000);</script>",
    unsafe_allow_html=True,
)
