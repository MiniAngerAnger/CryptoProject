"""Kronos 预测适配层（轻量版）

说明：
- 优先尝试导入本地/已安装的 Kronos 预测器
- 不可用时自动降级为 None（系统继续运行）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class KronosConfig:
    enabled: bool = False
    lookback: int = 240
    pred_len: int = 12
    model_name: str = "NeoQuasar/Kronos-small"
    tokenizer_name: str = "NeoQuasar/Kronos-Tokenizer-base"
    max_context: int = 512


class KronosAdapter:
    def __init__(self, cfg: KronosConfig):
        self.cfg = cfg
        self.ready = False
        self.predictor = None
        if not cfg.enabled:
            return
        self._try_init()

    def _try_init(self):
        try:
            # Kronos 官方示例路径
            from model import Kronos, KronosTokenizer, KronosPredictor  # type: ignore

            tokenizer = KronosTokenizer.from_pretrained(self.cfg.tokenizer_name)
            model = Kronos.from_pretrained(self.cfg.model_name)
            self.predictor = KronosPredictor(model, tokenizer, max_context=self.cfg.max_context)
            self.ready = True
            logger.info("[kronos] 预测器初始化成功")
        except Exception as e:
            logger.warning(f"[kronos] 未就绪，自动降级到 baseline: {e}")
            self.ready = False
            self.predictor = None

    def predict_close_delta(self, closes: list[float]) -> Optional[float]:
        """返回预测区间最后 close 相对当前 close 的百分比变化。

        返回：
        - float: 例如 0.012 表示 +1.2%
        - None: Kronos 不可用或数据不足
        """
        if not self.ready or not self.predictor:
            return None

        if len(closes) < max(32, self.cfg.lookback):
            return None

        try:
            closes = closes[-self.cfg.lookback:]
            now = pd.Timestamp.utcnow().floor("min")
            x_ts = pd.Series(pd.date_range(end=now, periods=len(closes), freq="1min"))
            y_ts = pd.Series(pd.date_range(start=now + pd.Timedelta(minutes=1), periods=self.cfg.pred_len, freq="1min"))

            x_df = pd.DataFrame({
                "open": closes,
                "high": closes,
                "low": closes,
                "close": closes,
                "volume": [0.0] * len(closes),
                "amount": [0.0] * len(closes),
            })

            pred = self.predictor.predict(
                df=x_df,
                x_timestamp=x_ts,
                y_timestamp=y_ts,
                pred_len=self.cfg.pred_len,
                T=1.0,
                top_p=0.9,
                sample_count=1,
            )

            if pred is None or pred.empty:
                return None

            last_pred_close = float(pred["close"].iloc[-1])
            cur_close = float(closes[-1])
            if cur_close == 0:
                return None
            return (last_pred_close - cur_close) / cur_close
        except Exception as e:
            logger.warning(f"[kronos] 预测失败，降级 baseline: {e}")
            return None
