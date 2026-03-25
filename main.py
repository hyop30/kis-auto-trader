import time
from datetime import datetime

from config import LOOP_SECONDS, DRY_RUN
from db import init_db, save_log
from kis_client import KISClient
from telegram_bot import send_telegram_message
from trader import Trader
from universe import UNIVERSE


def main():
    init_db()

    kis = KISClient()
    kis.ensure_access_token()

    trader = Trader(kis, UNIVERSE)

    boot_msg = f"[BOT START] loop={LOOP_SECONDS}s | dry_run={DRY_RUN} | universe={len(UNIVERSE)}"
    print(boot_msg)
    save_log("INFO", boot_msg)
    send_telegram_message(boot_msg)

    while True:
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            results = trader.run_once()

            msg = f"[CYCLE] {now}\n" + "\n".join(results)
            print(msg)
            save_log("INFO", msg)
            send_telegram_message(msg)

        except Exception as e:
            error_msg = f"[ERROR] {str(e)}"
            print(error_msg)
            save_log("ERROR", error_msg)
            send_telegram_message(error_msg)

        time.sleep(LOOP_SECONDS)


if __name__ == "__main__":
    main()