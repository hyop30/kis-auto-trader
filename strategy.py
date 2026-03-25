import pandas as pd
from config import STOP_LOSS_PCT, TAKE_PROFIT_PCT


def prepare_daily_df(price_list: list) -> pd.DataFrame:
    df = pd.DataFrame(price_list).copy()

    if df.empty:
        return df

    rename_map = {
        "stck_bsop_date": "date",
        "xymd": "date",
        "stck_clpr": "close",
        "stck_oprc": "open",
        "stck_hgpr": "high",
        "stck_lwpr": "low",
        "acml_vol": "volume",
        "cntg_vol": "volume",
    }

    for old, new in rename_map.items():
        if old in df.columns:
            df.rename(columns={old: new}, inplace=True)

    needed = ["date", "open", "high", "low", "close", "volume"]
    for col in needed:
        if col not in df.columns:
            df[col] = None

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["date"] = df["date"].astype(str)
    df = df.sort_values("date").reset_index(drop=True)

    df["ma5"] = df["close"].rolling(5).mean()
    df["ma20"] = df["close"].rolling(20).mean()
    df["ma60"] = df["close"].rolling(60).mean()
    df["high20"] = df["high"].rolling(20).max()
    df["low20"] = df["low"].rolling(20).min()
    df["ret1"] = df["close"].pct_change() * 100

    return df


def buy_signal_from_daily(df: pd.DataFrame) -> tuple[str, str]:
    if df.empty or len(df) < 70:
        return "HOLD", "일봉데이터부족"

    row = df.iloc[-1]

    close = float(row["close"])
    ma5 = float(row["ma5"])
    ma20 = float(row["ma20"])
    ma60 = float(row["ma60"])
    high20 = float(row["high20"])
    ret1 = float(row["ret1"]) if pd.notna(row["ret1"]) else 0.0
    volume = float(row["volume"]) if pd.notna(row["volume"]) else 0.0

    if pd.isna(ma5) or pd.isna(ma20) or pd.isna(ma60):
        return "HOLD", "이평계산불가"

    if volume < 100000:
        return "HOLD", "거래량부족"

    if close < ma20 * 0.97:
        return "HOLD", "종가가20일선아래"

    if close < ma60 * 0.97:
        return "HOLD", "종가가60일선보다너무아래"

    if ma20 < ma60 * 0.98:
        return "HOLD", "20일선이60일선보다약함"

    if ma5 < ma20 * 0.98:
        return "HOLD", "5일선이20일선아래"

    if ret1 > 7.0:
        return "HOLD", "당일급등과열"

    if high20 > 0 and close > high20 * 0.995:
        return "HOLD", "20일고점부근과열"

    return "BUY", "20일/60일추세상승"


def sell_signal_from_daily(avg_buy_price: float, df: pd.DataFrame) -> tuple[str, str]:
    if df.empty:
        return "HOLD", "일봉데이터없음"

    row = df.iloc[-1]
    close = float(row["close"])
    ma20 = float(row["ma20"]) if pd.notna(row["ma20"]) else 0.0
    ma60 = float(row["ma60"]) if pd.notna(row["ma60"]) else 0.0

    if avg_buy_price <= 0 or close <= 0:
        return "HOLD", "가격정보부족"

    pnl_pct = ((close - avg_buy_price) / avg_buy_price) * 100

    if pnl_pct <= -STOP_LOSS_PCT:
        return "SELL", f"손절({pnl_pct:.2f}%)"

    if pnl_pct >= TAKE_PROFIT_PCT:
        return "SELL", f"익절({pnl_pct:.2f}%)"

    if ma20 > 0 and close < ma20:
        return "SELL", f"20일선이탈({pnl_pct:.2f}%)"

    if ma60 > 0 and close < ma60:
        return "SELL", f"60일선이탈({pnl_pct:.2f}%)"

    return "HOLD", f"보유유지({pnl_pct:.2f}%)"


def simple_backtest(df: pd.DataFrame) -> dict:
    if df.empty or len(df) < 70:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "total_return_pct": 0.0,
        }

    in_position = False
    buy_price = 0.0
    returns = []

    for i in range(60, len(df)):
        row = df.iloc[i]
        close = float(row["close"])
        ma5 = row["ma5"]
        ma20 = row["ma20"]
        ma60 = row["ma60"]

        if pd.isna(ma5) or pd.isna(ma20) or pd.isna(ma60):
            continue

        if not in_position:
            if close > ma20 and close > ma60 and ma5 > ma20 and ma20 > ma60:
                in_position = True
                buy_price = close
        else:
            if close < ma20 or close < ma60:
                ret = ((close - buy_price) / buy_price) * 100
                returns.append(ret)
                in_position = False
                buy_price = 0.0

    if in_position and buy_price > 0:
        close = float(df.iloc[-1]["close"])
        ret = ((close - buy_price) / buy_price) * 100
        returns.append(ret)

    if not returns:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "total_return_pct": 0.0,
        }

    wins = sum(1 for r in returns if r > 0)
    total_return = sum(returns)

    return {
        "trades": len(returns),
        "win_rate": round((wins / len(returns)) * 100, 2),
        "total_return_pct": round(total_return, 2),
    }

def opening_breakout_signal(price_data: dict):
    output = price_data.get("output", {})

    price = float(output.get("stck_prpr", 0) or 0)
    open_price = float(output.get("stck_oprc", 0) or 0)
    high_price = float(output.get("stck_hgpr", 0) or 0)
    volume = int(float(output.get("acml_vol", 0) or 0))

    if price <= 0 or open_price <= 0:
        return "HOLD", "가격정보없음"

    change_pct = ((price - open_price) / open_price) * 100

    if change_pct < 0.8:
        return "HOLD", "시가대비상승부족"

    if volume < 50000:
        return "HOLD", "거래량부족"

    if high_price > 0 and price < high_price * 0.995:
        return "HOLD", "고가근처아님"

    if change_pct > 4.5:
        return "HOLD", "과열"

    return "BUY", f"장초돌파 {change_pct:.2f}%"

from config import (
    STOP_LOSS_PCT,
    TAKE_PROFIT_PCT,
    OPENING_STOP_LOSS_PCT,
    OPENING_TAKE_PROFIT_PCT,
    OPENING_MAX_CHASE_PCT,
)

def opening_breakout_signal(price_data: dict):
    output = price_data.get("output", {})

    price = float(output.get("stck_prpr", 0) or 0)
    open_price = float(output.get("stck_oprc", 0) or 0)
    high_price = float(output.get("stck_hgpr", 0) or 0)
    volume = int(float(output.get("acml_vol", 0) or 0))

    if price <= 0 or open_price <= 0:
        return "HOLD", "가격정보없음"

    change_pct = ((price - open_price) / open_price) * 100

    if change_pct < 0.8:
        return "HOLD", "시가대비상승부족"

    if volume < 50000:
        return "HOLD", "거래량부족"

    if high_price > 0 and price < high_price * 0.995:
        return "HOLD", "고가근처아님"

    if change_pct > OPENING_MAX_CHASE_PCT:
        return "HOLD", "과열"

    return "BUY", f"장초돌파 {change_pct:.2f}%"


def opening_exit_signal(avg_buy_price: float, price_data: dict):
    output = price_data.get("output", {})

    current_price = float(output.get("stck_prpr", 0) or 0)
    open_price = float(output.get("stck_oprc", 0) or 0)
    high_price = float(output.get("stck_hgpr", 0) or 0)

    if avg_buy_price <= 0 or current_price <= 0:
        return "HOLD", "가격정보없음"

    pnl_pct = ((current_price - avg_buy_price) / avg_buy_price) * 100

    if pnl_pct <= -OPENING_STOP_LOSS_PCT:
        return "SELL", f"장초손절 {pnl_pct:.2f}%"

    if pnl_pct >= OPENING_TAKE_PROFIT_PCT:
        return "SELL", f"장초익절 {pnl_pct:.2f}%"

    # 시가 아래 + 고가 대비 밀림이면 약세 전환으로 판단
    if open_price > 0 and current_price < open_price:
        if high_price > 0 and current_price < high_price * 0.992:
            return "SELL", f"장초약세전환 {pnl_pct:.2f}%"

    return "HOLD", f"장초보유 {pnl_pct:.2f}%"