import pandas as pd
from strategy import prepare_daily_df


def calc_score(df: pd.DataFrame) -> dict:
    if df.empty or len(df) < 70:
        return {"passed": False, "score": -999, "reason": "데이터부족"}

    row = df.iloc[-1]

    close = float(row["close"])
    ma5 = float(row["ma5"])
    ma20 = float(row["ma20"])
    ma60 = float(row["ma60"])
    high20 = float(row["high20"])
    volume = float(row["volume"])
    ret1 = float(row["ret1"]) if pd.notna(row["ret1"]) else 0.0

    if pd.isna(ma20) or pd.isna(ma60):
        return {"passed": False, "score": -999, "reason": "이평계산불가"}

    if close < ma60 * 0.97:
        return {"passed": False, "score": -999, "reason": "종가가60일선보다너무아래"}

    if ma20 < ma60 * 0.98:
        return {"passed": False, "score": -999, "reason": "20일선이60일선보다약함"}

    if volume < 100000:
        return {"passed": False, "score": -999, "reason": "거래량부족"}

    if ret1 > 8.0:
        return {"passed": False, "score": -999, "reason": "당일과열"}

    score = 0.0
    score += ((close / ma20) - 1.0) * 100 * 2.0
    score += ((close / ma60) - 1.0) * 100 * 1.5
    score += ((ma20 / ma60) - 1.0) * 100 * 2.0

    if high20 > 0:
        proximity = (close / high20) * 100
        if 96 <= proximity <= 99.5:
            score += 8
        elif 92 <= proximity < 96:
            score += 4
        elif proximity > 99.5:
            score -= 3

    if ma5 > ma20:
        score += 5
    else:
        score -= 3

    if ret1 > 5.0:
        score -= 4
    elif 1.0 <= ret1 <= 3.5:
        score += 3

    return {"passed": True, "score": round(score, 2), "reason": "통과"}


def select_top_candidates(kis_client, universe: dict, top_n: int = 5):
    selected = []
    rejected = []

    for symbol, name in universe.items():
        daily_data = kis_client.get_daily_prices(symbol)
        daily_list = daily_data.get("output2", []) or daily_data.get("output", [])
        df = prepare_daily_df(daily_list)

        result = calc_score(df)

        if not result["passed"]:
            rejected.append({
                "symbol": symbol,
                "name": name,
                "reason": result["reason"],
            })
            continue

        row = df.iloc[-1]
        selected.append({
            "symbol": symbol,
            "name": name,
            "score": result["score"],
            "close": float(row["close"]),
            "ma20": float(row["ma20"]),
            "ma60": float(row["ma60"]),
            "ret1": float(row["ret1"]) if pd.notna(row["ret1"]) else 0.0,
            "volume": int(row["volume"]) if pd.notna(row["volume"]) else 0,
        })

    selected.sort(key=lambda x: x["score"], reverse=True)
    return selected[:top_n], rejected


def select_top_turnover_symbols(kis_client, universe: dict, top_n: int = 5):
    """
    거래대금 기준 상위 종목 선별
    거래대금 = 현재가 * 누적거래량
    """
    ranked = []

    for symbol, name in universe.items():
        try:
            price_data = kis_client.get_current_price(symbol)
            output = price_data.get("output", {})

            price = float(output.get("stck_prpr", 0) or 0)
            volume = int(float(output.get("acml_vol", 0) or 0))
            rate = float(output.get("prdy_ctrt", 0) or 0)

            turnover = price * volume

            if price <= 0 or volume <= 0:
                continue

            ranked.append({
                "symbol": symbol,
                "name": name,
                "price": price,
                "volume": volume,
                "turnover": turnover,
                "rate": rate,
            })
        except Exception:
            continue

    ranked.sort(key=lambda x: x["turnover"], reverse=True)
    return ranked[:top_n]