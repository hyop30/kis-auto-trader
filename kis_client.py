import json
from datetime import datetime, timedelta
from pathlib import Path

import requests

from config import (
    KIS_APP_KEY,
    KIS_APP_SECRET,
    KIS_BASE_URL,
    KIS_ACCOUNT_NO,
    KIS_ACCOUNT_PRODUCT_CD,
    KIS_ENV,
)

TOKEN_FILE = Path("data/kis_token.json")


class KISClient:
    def __init__(self):
        self.app_key = KIS_APP_KEY
        self.app_secret = KIS_APP_SECRET
        self.base_url = KIS_BASE_URL
        self.account_no = KIS_ACCOUNT_NO
        self.account_product_cd = KIS_ACCOUNT_PRODUCT_CD
        self.env = KIS_ENV
        self.access_token = None

    def _save_token(self, token: str, expires_in: int):
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        expires_at = datetime.now() + timedelta(seconds=max(expires_in - 60, 60))
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "access_token": token,
                "expires_at": expires_at.isoformat(),
            }, f, ensure_ascii=False, indent=2)

    def _load_token(self):
        if not TOKEN_FILE.exists():
            return None
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            token = data.get("access_token")
            expires_at = datetime.fromisoformat(data.get("expires_at"))
            if token and datetime.now() < expires_at:
                return token
        except Exception:
            return None
        return None

    def get_access_token(self):
        url = f"{self.base_url}/oauth2/tokenP"
        headers = {"content-type": "application/json; charset=utf-8"}
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }
        res = requests.post(url, json=body, headers=headers, timeout=10)
        data = res.json()
        if res.status_code != 200:
            raise RuntimeError(f"KIS token 발급 실패 | status={res.status_code} | response={data}")

        self.access_token = data["access_token"]
        self._save_token(self.access_token, int(data.get("expires_in", 86400)))
        return self.access_token

    def ensure_access_token(self):
        cached = self._load_token()
        if cached:
            self.access_token = cached
            return cached
        return self.get_access_token()

    def _auth_headers(self, tr_id: str, hashkey: str = None):
        if not self.access_token:
            raise RuntimeError("먼저 ensure_access_token()을 호출하세요.")
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }
        if hashkey:
            headers["hashkey"] = hashkey
        return headers

    def get_hashkey(self, body: dict) -> str:
        url = f"{self.base_url}/uapi/hashkey"
        headers = {
            "content-type": "application/json; charset=utf-8",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }
        res = requests.post(url, headers=headers, json=body, timeout=10)
        data = res.json()
        if res.status_code != 200:
            raise RuntimeError(f"Hashkey 발급 실패 | status={res.status_code} | response={data}")
        return data["HASH"]

    def get_current_price(self, symbol: str):
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        headers = self._auth_headers(tr_id="FHKST01010100")
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": symbol,
        }
        res = requests.get(url, headers=headers, params=params, timeout=10)
        data = res.json()
        if res.status_code != 200:
            raise RuntimeError(f"현재가 조회 실패 | status={res.status_code} | response={data}")
        return data

    def get_balance(self):
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
        headers = self._auth_headers(tr_id="VTTC8434R" if self.env == "mock" else "TTTC8434R")
        params = {
            "CANO": self.account_no,
            "ACNT_PRDT_CD": self.account_product_cd,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        res = requests.get(url, headers=headers, params=params, timeout=10)
        data = res.json()
        if res.status_code != 200:
            raise RuntimeError(f"잔고 조회 실패 | status={res.status_code} | response={data}")
        return data

    def place_cash_order(self, side: str, symbol: str, qty: int, price: int, order_type: str = "00"):
        """
        side: BUY / SELL
        order_type: 00 지정가, 01 시장가(환경별 세부 규칙은 공식문서 확인)
        """
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/order-cash"

        tr_id_map = {
            ("mock", "BUY"): "VTTC0802U",
            ("mock", "SELL"): "VTTC0801U",
            ("live", "BUY"): "TTTC0802U",
            ("live", "SELL"): "TTTC0801U",
        }
        tr_id = tr_id_map[(self.env, side)]

        body = {
            "CANO": self.account_no,
            "ACNT_PRDT_CD": self.account_product_cd,
            "PDNO": symbol,
            "ORD_DVSN": order_type,
            "ORD_QTY": str(int(qty)),
            "ORD_UNPR": str(int(price)),
        }

        hashkey = self.get_hashkey(body)
        headers = self._auth_headers(tr_id=tr_id, hashkey=hashkey)

        res = requests.post(url, headers=headers, json=body, timeout=10)
        try:
            data = res.json()
        except Exception:
            data = {"raw": res.text}

        if res.status_code != 200:
            raise RuntimeError(f"주문 실패 | status={res.status_code} | response={data}")

        return data
    
    def get_daily_prices(self, symbol: str, period_div_code: str = "D", adj_price: str = "1"):
        """
        symbol: 종목코드 (예: 005930)
        period_div_code: D(일), W(주), M(월), Y(년)
        adj_price: 1 수정주가 반영
        """
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        headers = self._auth_headers(tr_id="FHKST03010100")
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": symbol,
            "FID_INPUT_DATE_1": "",
            "FID_INPUT_DATE_2": "",
            "FID_PERIOD_DIV_CODE": period_div_code,
            "FID_ORG_ADJ_PRC": adj_price,
        }

        res = requests.get(url, headers=headers, params=params, timeout=10)
        try:
            data = res.json()
        except Exception:
            data = {"raw": res.text}

        if res.status_code != 200:
            raise RuntimeError(
                f"일봉 조회 실패 | status={res.status_code} | response={data}"
            )

        return data
    
    def get_order_status(self, order_no: str = "", symbol: str = ""):
        """
        주식일별주문체결조회
        반환 구조는 환경에 따라 output1/output2 키가 다를 수 있으니 원본 JSON을 그대로 사용
        """
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-daily-ccld"
        headers = self._auth_headers(tr_id="VTTC8001R" if self.env == "mock" else "TTTC8001R")

        params = {
            "CANO": self.account_no,
            "ACNT_PRDT_CD": self.account_product_cd,
            "INQR_STRT_DT": "",
            "INQR_END_DT": "",
            "SLL_BUY_DVSN_CD": "00",
            "INQR_DVSN": "00",
            "PDNO": symbol,
            "CCLD_DVSN": "00",
            "ORD_GNO_BRNO": "",
            "ODNO": order_no,
            "INQR_DVSN_3": "00",
            "INQR_DVSN_1": "",
        }

        res = requests.get(url, headers=headers, params=params, timeout=10)
        try:
            data = res.json()
        except Exception:
            data = {"raw": res.text}

        if res.status_code != 200:
            raise RuntimeError(f"체결조회 실패 | status={res.status_code} | response={data}")

        return data

    def cancel_order(self, org_order_no: str, symbol: str, qty: int, price: int = 0):
        """
        주식주문(정정취소)
        취소 요청. 모의/실전 TR ID는 환경별로 다를 수 있어 첫 실행 응답 확인 필요.
        """
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/order-rvsecncl"

        tr_id_map = {
            "mock": "VTTC0803U",
            "live": "TTTC0803U",
        }
        tr_id = tr_id_map[self.env]

        body = {
            "CANO": self.account_no,
            "ACNT_PRDT_CD": self.account_product_cd,
            "KRX_FWDG_ORD_ORGNO": "",
            "ORGN_ODNO": org_order_no,
            "ORD_DVSN": "00",
            "RVSE_CNCL_DVSN_CD": "02",  # 01 정정, 02 취소로 많이 사용
            "PDNO": symbol,
            "ORD_QTY": str(int(qty)),
            "ORD_UNPR": str(int(price)),
            "QTY_ALL_ORD_YN": "Y",
        }

        hashkey = self.get_hashkey(body)
        headers = self._auth_headers(tr_id=tr_id, hashkey=hashkey)

        res = requests.post(url, headers=headers, json=body, timeout=10)
        try:
            data = res.json()
        except Exception:
            data = {"raw": res.text}

        if res.status_code != 200:
            raise RuntimeError(f"취소주문 실패 | status={res.status_code} | response={data}")

        return data