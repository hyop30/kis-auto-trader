import json
import time
from datetime import datetime

from config import (
    DRY_RUN,
    MAX_BUY_KRW_PER_TRADE,
    MAX_POSITIONS,
    ORDER_CHECK_WAIT_SECONDS,
    ORDER_CANCEL_AFTER_SECONDS,
    FORCE_BUY_TEST,
    TEST_SYMBOL,
)

from db import (
    save_log,
    save_signal,
    save_order,
    save_price_snapshot,
    count_open_like_buy_orders_today,
    update_order_status,
)

from strategy import (
    prepare_daily_df,
    buy_signal_from_daily,
    sell_signal_from_daily,
    simple_backtest,
    opening_breakout_signal,
    opening_exit_signal,
)

from selector import (
    select_top_candidates,
    select_top_turnover_symbols,
)


class Trader:
    def __init__(self, kis_client, universe: dict):
        self.kis = kis_client
        self.universe = universe

    def _safe_float(self, v, default=0.0):
        try:
            return float(v)
        except Exception:
            return default

    def _safe_int(self, v, default=0):
        try:
            return int(float(v))
        except Exception:
            return default

    def _order_qty(self, price):
        if price <= 0:
            return 0
        return max(int(MAX_BUY_KRW_PER_TRADE // price), 0)

    def _holding_map(self, balance_data):
        holdings = {}
        for item in balance_data.get("output1", []):
            symbol = item.get("pdno") or item.get("stck_shrn_iscd") or item.get("prdt_no")
            qty = self._safe_int(item.get("hldg_qty"))
            avg_price = self._safe_float(item.get("pchs_avg_pric"))

            if qty > 0 and symbol:
                holdings[symbol] = {
                    "qty": qty,
                    "avg_price": avg_price
                }
        return holdings

    def _extract_order_no(self, res):
        if not isinstance(res, dict):
            return None
        output = res.get("output", {}) or {}
        return output.get("ODNO") or output.get("odno")

    def _classify_order_status(self, data):
        text = json.dumps(data, ensure_ascii=False)

        if "체결" in text:
            return "FILLED"
        if "미체결" in text:
            return "PENDING"
        return "UNKNOWN"

    def _submit_and_manage_order(self, side, symbol, name, qty, price, reason):
        if DRY_RUN:
            return f"[DRY {side}] {name} {qty}주 @ {price} | {reason}"

        res = self.kis.place_cash_order(side, symbol, qty, price)
        order_no = self._extract_order_no(res)

        order_id = save_order(
            symbol,
            name,
            side,
            qty,
            price,
            "00",
            "SUBMITTED",
            order_no,
            json.dumps(res, ensure_ascii=False)
        )

        msg = f"[{side}] {name} {qty}주 @ {price} | 주문번호={order_no} | {reason}"
        save_log("INFO", msg)

        time.sleep(ORDER_CHECK_WAIT_SECONDS)

        status = self.kis.get_order_status(order_no, symbol)
        state = self._classify_order_status(status)

        update_order_status(order_id, state, json.dumps(status, ensure_ascii=False))

        if state == "FILLED":
            return msg + "\n→ 체결 완료"

        time.sleep(ORDER_CANCEL_AFTER_SECONDS)

        cancel_res = self.kis.cancel_order(order_no, symbol, qty, price)
        update_order_status(order_id, "CANCELLED", json.dumps(cancel_res, ensure_ascii=False))

        return msg + "\n→ 미체결 → 취소"

    def run_once(self):
        results = []

        # 강제 테스트
        if FORCE_BUY_TEST:
            symbol = TEST_SYMBOL
            name = self.universe.get(symbol, symbol)

            price_data = self.kis.get_current_price(symbol)
            price = int(float(price_data.get("output", {}).get("stck_prpr", 0) or 0))
            qty = self._order_qty(price)

            if qty > 0:
                msg = self._submit_and_manage_order("BUY", symbol, name, qty, price, "테스트")
                return [msg]

        now = datetime.now()

        # 현재 보유 종목 항상 먼저 확인
        balance = self.kis.get_balance()
        holdings = self._holding_map(balance)

        # =========================
        # 장초반 전략
        # =========================
        if now.hour == 9 and now.minute <= 30:
            results.append("[OPENING STRATEGY]")

            # 1. 보유 종목 장초반 빠른 청산 판단
            for symbol, hold in holdings.items():
                name = self.universe.get(symbol, symbol)
                price_data = self.kis.get_current_price(symbol)
                output = price_data.get("output", {})

                current_price = self._safe_float(output.get("stck_prpr", 0))
                diff = self._safe_float(output.get("prdy_vrss", 0))
                rate = self._safe_float(output.get("prdy_ctrt", 0))
                volume = self._safe_int(output.get("acml_vol", 0))

                save_price_snapshot(symbol, name, current_price, diff, rate, volume)

                action, reason = opening_exit_signal(hold["avg_price"], price_data)
                save_signal(symbol, name, action, reason, current_price)

                if action == "SELL":
                    msg = self._submit_and_manage_order(
                        "SELL",
                        symbol,
                        name,
                        hold["qty"],
                        int(current_price),
                        reason
                    )
                    results.append(msg)
                else:
                    results.append(
                        f"[OPEN HOLD] {name}({symbol}) {hold['qty']}주 "
                        f"| 현재가 {int(current_price)} | 평단 {int(hold['avg_price'])} | {reason}"
                    )

            # 2. 거래대금 상위 종목 신규 진입
            top_turnover = select_top_turnover_symbols(self.kis, self.universe, 5)

            if top_turnover:
                rank_msg = "[TOP TURNOVER]\n" + "\n".join(
                    f"{i+1}. {x['name']}({x['symbol']}) "
                    f"가격={int(x['price'])} 거래량={x['volume']} "
                    f"거래대금={int(x['turnover'])} 등락률={round(x['rate'], 2)}%"
                    for i, x in enumerate(top_turnover)
                )
                results.append(rank_msg)
            else:
                results.append("[TOP TURNOVER] 후보 없음")
                return results

            open_position_count = len(holdings)

            for item in top_turnover:
                symbol = item["symbol"]
                name = item["name"]

                if symbol in holdings:
                    results.append(f"[SKIP] {name}({symbol}) | 이미 보유 중")
                    continue

                if open_position_count >= MAX_POSITIONS:
                    results.append(f"[SKIP] {name}({symbol}) | 최대 보유 종목 수 초과")
                    continue

                if count_open_like_buy_orders_today(symbol) > 0:
                    results.append(f"[SKIP] {name}({symbol}) | 오늘 이미 매수 시도함")
                    continue

                price_data = self.kis.get_current_price(symbol)
                output = price_data.get("output", {})

                current_price = self._safe_float(output.get("stck_prpr", 0))
                diff = self._safe_float(output.get("prdy_vrss", 0))
                rate = self._safe_float(output.get("prdy_ctrt", 0))
                volume = self._safe_int(output.get("acml_vol", 0))

                save_price_snapshot(symbol, name, current_price, diff, rate, volume)

                action, reason = opening_breakout_signal(price_data)
                save_signal(symbol, name, action, reason, current_price)

                if action != "BUY":
                    results.append(f"[HOLD] {name}({symbol}) | {reason}")
                    continue

                price = int(current_price)
                qty = self._order_qty(price)

                if qty <= 0:
                    results.append(f"[SKIP] {name}({symbol}) | 주문가능수량 0")
                    continue

                msg = self._submit_and_manage_order(
                    "BUY",
                    symbol,
                    name,
                    qty,
                    price,
                    reason
                )
                results.append(msg)
                open_position_count += 1

            return results

        # =========================
        # 일반 전략 (일봉)
        # =========================
        top_candidates, rejected = select_top_candidates(self.kis, self.universe)

        if top_candidates:
            rank_msg = "[TOP CANDIDATES]\n" + "\n".join(
                f"{i+1}. {x['name']}({x['symbol']}) score={x['score']} close={int(x['close'])} "
                f"ma20={int(x['ma20'])} ma60={int(x['ma60'])} ret1={round(x['ret1'], 2)}%"
                for i, x in enumerate(top_candidates)
            )
            results.append(rank_msg)
        else:
            reject_msg = "[NO CANDIDATES]\n" + "\n".join(
                f"- {x['name']}({x['symbol']}) 탈락:{x['reason']}"
                for x in rejected[:10]
            )
            results.append(reject_msg)

        symbols_to_check = set([x["symbol"] for x in top_candidates]) | set(holdings.keys())

        for symbol in symbols_to_check:
            name = self.universe.get(symbol, symbol)

            daily_data = self.kis.get_daily_prices(symbol)
            daily_list = daily_data.get("output2", []) or daily_data.get("output", [])
            df = prepare_daily_df(daily_list)

            if df.empty:
                results.append(f"[SKIP] {name}({symbol}) | 일봉 데이터 없음")
                continue

            last = df.iloc[-1]
            current_price = self._safe_float(last["close"])
            prev_close = self._safe_float(df.iloc[-2]["close"]) if len(df) >= 2 else current_price
            diff = current_price - prev_close
            rate = self._safe_float(last["ret1"]) if "ret1" in df.columns else 0.0
            volume = self._safe_int(last["volume"])

            save_price_snapshot(symbol, name, current_price, diff, rate, volume)
            bt = simple_backtest(df)

            if symbol in holdings:
                hold = holdings[symbol]
                action, reason = sell_signal_from_daily(hold["avg_price"], df)
                reason = f"{reason} | BT:{bt['trades']}회 승률{bt['win_rate']}% 누적{bt['total_return_pct']}%"
                save_signal(symbol, name, action, reason, current_price)

                if action == "SELL":
                    msg = self._submit_and_manage_order(
                        "SELL",
                        symbol,
                        name,
                        hold["qty"],
                        int(current_price),
                        reason
                    )
                    results.append(msg)
                else:
                    results.append(
                        f"[HOLD] {name}({symbol}) 보유 {hold['qty']}주 "
                        f"| 종가 {int(current_price)} | 매입가 {int(hold['avg_price'])} | {reason}"
                    )
                continue

            if len(holdings) >= MAX_POSITIONS:
                results.append(f"[SKIP] {name}({symbol}) | 최대 보유 종목 수 초과")
                continue

            if count_open_like_buy_orders_today(symbol) > 0:
                results.append(f"[SKIP] {name}({symbol}) | 오늘 이미 매수 시도함")
                continue

            action, reason = buy_signal_from_daily(df)
            reason = f"{reason} | BT:{bt['trades']}회 승률{bt['win_rate']}% 누적{bt['total_return_pct']}%"
            save_signal(symbol, name, action, reason, current_price)

            if action != "BUY":
                results.append(f"[HOLD] {name}({symbol}) | 종가 {int(current_price)} | {reason}")
                continue

            qty = self._order_qty(current_price)
            if qty <= 0:
                results.append(f"[SKIP] {name}({symbol}) | 주문가능수량 0")
                continue

            msg = self._submit_and_manage_order(
                "BUY",
                symbol,
                name,
                qty,
                int(current_price),
                reason
            )
            results.append(msg)

        return results