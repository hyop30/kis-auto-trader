import os
from dotenv import load_dotenv

load_dotenv()

KIS_APP_KEY = os.getenv("KIS_APP_KEY")
KIS_APP_SECRET = os.getenv("KIS_APP_SECRET")
KIS_ACCOUNT_NO = os.getenv("KIS_ACCOUNT_NO")
KIS_ACCOUNT_PRODUCT_CD = os.getenv("KIS_ACCOUNT_PRODUCT_CD", "01")
KIS_BASE_URL = os.getenv("KIS_BASE_URL")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# mock / live
KIS_ENV = os.getenv("KIS_ENV", "mock").lower()

# 안전장치: 처음엔 반드시 True
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"

# 루프 간격(초) - 5분
LOOP_SECONDS = int(os.getenv("LOOP_SECONDS", "300"))

# 리스크 제한
MAX_POSITIONS = int(os.getenv("MAX_POSITIONS", "3"))
MAX_BUY_KRW_PER_TRADE = int(os.getenv("MAX_BUY_KRW_PER_TRADE", "300000"))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "3.0"))
TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", "5.0"))

FORCE_BUY_TEST = True
FORCE_SELL_TEST = False
TEST_SYMBOL = "005930"

ORDER_CHECK_WAIT_SECONDS = int(os.getenv("ORDER_CHECK_WAIT_SECONDS", "5"))
ORDER_CANCEL_AFTER_SECONDS = int(os.getenv("ORDER_CANCEL_AFTER_SECONDS", "20"))

FORCE_BUY_TEST = os.getenv("FORCE_BUY_TEST", "false").lower() == "true"
FORCE_SELL_TEST = os.getenv("FORCE_SELL_TEST", "false").lower() == "true"
TEST_SYMBOL = os.getenv("TEST_SYMBOL", "005930")

OPENING_STOP_LOSS_PCT = float(os.getenv("OPENING_STOP_LOSS_PCT", "1.2"))
OPENING_TAKE_PROFIT_PCT = float(os.getenv("OPENING_TAKE_PROFIT_PCT", "2.0"))
OPENING_MAX_CHASE_PCT = float(os.getenv("OPENING_MAX_CHASE_PCT", "4.5"))