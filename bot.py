import os
import json
import asyncio
import requests
import websockets
from datetime import datetime, timezone
from dotenv import load_dotenv
from fastapi import FastAPI
import uvicorn

load_dotenv()

# ─── Configuration & Globals ─────────────────────────────────────────────
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
USER_ID = os.getenv("TELEGRAM_USER_ID")

WALLETS = [
    "dUJNHh9Nm9rsn7ykTViG7N7BJuaoJJD9H635B8BVifa",
    "6KK9rw7aU7HaLiHPiXHStcpSnSXuH5w7oh8Aa5ecT6Ck",
    "9B1fR2Z38ggjqmFuhYBEsa7fXaBR1dkC7BamixjmWZb4"
]

RPC_WS = "wss://api.mainnet-beta.solana.com/"
THRESHOLD = int(20 * 1e9)  # 20 SOL

subs = {}
balances = {}

# ------------------ FASTAPI (UPTIME) SETUP ------------------
fast_app = FastAPI()

@fast_app.get("/")
async def root():
    return {"status": "OK"}

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(fast_app, host="0.0.0.0", port=port)

# ─── Utility Functions ───────────────────────────────────────────────────
def timestamp():
    return datetime.now(timezone.utc).isoformat()

def notify_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    res = requests.post(url, data={"chat_id": USER_ID, "text": message})
    print("Telegram response:", res.status_code, res.text)
    if res.status_code != 200:
        print(f"[{timestamp()}] ⚠️ Telegram error:", res.text)

# ─── Wallet Subscription + Monitoring ────────────────────────────────────
async def subscribe_wallets(ws):
    for i, wallet in enumerate(WALLETS, 1):
        req = {
            "jsonrpc": "2.0",
            "id": i,
            "method": "accountSubscribe",
            "params": [wallet, {"encoding": "base64"}]
        }
        await ws.send(json.dumps(req))
        resp = json.loads(await ws.recv())
        sub_id = resp.get("result")
        subs[sub_id] = wallet
        balances[wallet] = None

async def listen_transactions():
    async with websockets.connect(RPC_WS, ping_interval=30) as ws:
        await subscribe_wallets(ws)
        print(f"[{timestamp()}] ✅ Subscribed to {len(WALLETS)} wallets.")

        async for raw in ws:
            msg = json.loads(raw)
            if msg.get("method") != "accountNotification":
                continue

            params = msg["params"]
            sub_id = params["subscription"]
            wallet = subs.get(sub_id)
            data = params["result"]["value"]
            lamports = data.get("lamports")

            if balances[wallet] is None:
                balances[wallet] = lamports
                continue

            diff = lamports - balances[wallet]
            balances[wallet] = lamports

            if diff < 0 and abs(diff) >= THRESHOLD:
                sol = abs(diff) / 1e9
                message = (
                    f"🚨 {sol:.2f} SOL sent from {wallet}\n"
                    f"Time: {timestamp()}\n"
                    f"https://solscan.io/account/{wallet}"
                )
                notify_telegram(message)
                print(f"[{timestamp()}] ✉️ Alert: {wallet} -{sol:.2f} SOL")

async def run_forever():
    delay = 1
    while True:
        try:
            await listen_transactions()
        except Exception as err:
            print(f"[{timestamp()}] 🔁 Error: {err} — retrying in {delay}s")
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)
        else:
            delay = 1

# ─── Main Entrypoint ────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"[{timestamp()}] 🔌 Starting Solana Wallet Monitor…")
    # Start web server for Render uptime
    import threading
    threading.Thread(target=run_web_server, daemon=True).start()

    # Run the monitoring loop
    asyncio.run(run_forever())
    

