# BTC BB Optimised Trading Bot

Automated BTC/USDT Futures trading bot using the Optimised Bollinger Band strategy.
**Strategy:** BB (20, 1SD) on 1H | 5 filters | 1% risk per trade | max 2 signals/day

---

## Files
```
btc_bb_bot/
├── bot.py          ← Strategy engine, signal detection, order execution
├── app.py          ← Flask web dashboard + REST API
├── requirements.txt
├── Procfile        ← For Heroku / Render / Railway
├── .env.example    ← Copy to .env and fill in your keys
└── README.md
```

---

## Step 1 — Get your Binance API keys

1. Log into **Binance** → click your profile icon → **API Management**
2. Click **Create API** → choose **System Generated**
3. Name it (e.g. "BB Bot")
4. Under permissions, enable:
   - ✅ Enable Reading
   - ✅ Enable Futures
   - ❌ Enable Withdrawals  ← LEAVE THIS OFF
5. Under **IP Access Restrictions** → set your server's IP address
6. Copy the **API Key** and **Secret Key** — you only see the secret once

### Test first (strongly recommended)
Before going live, test on Binance Futures Testnet:
- Register at: https://testnet.binancefuture.com
- Get testnet API keys from that dashboard
- Set `TESTNET=true` in your `.env` file

---

## Step 2 — Run locally (for testing)

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and edit environment file
cp .env.example .env
# Edit .env with your API keys and TESTNET=true

# Start the bot
python app.py
# Dashboard: http://localhost:5000
```

---

## Step 3 — Deploy to a hosting provider

Pick one of the following. The bot needs to run 24/7.

### Option A — Render.com (Recommended, free tier available)

1. Push this folder to a GitHub repo
2. Go to https://render.com → **New Web Service**
3. Connect your GitHub repo
4. Settings:
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `gunicorn app:app --workers 1 --threads 4 --timeout 120`
   - **Instance type:** Starter ($7/mo) — free tier spins down and will miss signals
5. Under **Environment** → add:
   ```
   BINANCE_API_KEY     = your_key
   BINANCE_API_SECRET  = your_secret
   TESTNET             = true   (change to false when ready for live)
   ```
6. Deploy → visit your URL → click **▶ Start** on the dashboard

### Option B — Railway.app

1. Install Railway CLI: `npm install -g @railway/cli`
2. `railway login`
3. `railway init` inside the project folder
4. Set environment variables:
   ```
   railway variables set BINANCE_API_KEY=your_key
   railway variables set BINANCE_API_SECRET=your_secret
   railway variables set TESTNET=true
   ```
5. `railway up`

### Option C — Heroku

1. Install Heroku CLI and login
2. `heroku create your-bot-name`
3. Set config vars:
   ```
   heroku config:set BINANCE_API_KEY=your_key
   heroku config:set BINANCE_API_SECRET=your_secret
   heroku config:set TESTNET=true
   ```
4. `git push heroku main`
5. `heroku ps:scale web=1`

### Option D — VPS (DigitalOcean / Linode / Hetzner)

```bash
# On your VPS (Ubuntu 22.04):
sudo apt update && sudo apt install python3-pip python3-venv git -y
git clone <your_repo> btc_bb_bot
cd btc_bb_bot
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env && nano .env   # fill in keys

# Run with systemd (auto-restarts on crash)
sudo nano /etc/systemd/system/bbbot.service
```

Paste this into the service file:
```
[Unit]
Description=BTC BB Trading Bot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/btc_bb_bot
EnvironmentFile=/home/ubuntu/btc_bb_bot/.env
ExecStart=/home/ubuntu/btc_bb_bot/venv/bin/gunicorn app:app --workers 1 --threads 4 --timeout 120 --bind 0.0.0.0:5000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable bbbot
sudo systemctl start bbbot
sudo systemctl status bbbot
# Dashboard: http://YOUR_VPS_IP:5000
```

---

## Dashboard endpoints

| URL              | Description                        |
|------------------|------------------------------------|
| `/`              | Live trading dashboard             |
| `/api/status`    | JSON: bot status, active trade, log|
| `/api/balance`   | JSON: USDT futures wallet balance  |
| `/api/start`     | POST: start the bot                |
| `/api/stop`      | POST: stop the bot                 |
| `/api/log`       | JSON: last 100 lines of bot.log    |
| `/api/config`    | JSON: current strategy config      |

---

## Strategy rules (implemented in bot.py)

| Parameter          | Value                          |
|--------------------|-------------------------------|
| Timeframe          | 1 Hour                        |
| Bollinger Bands    | Period 20, **1 SD** (not 2)   |
| Long signal        | 1H candle closes above BB     |
| Short signal       | 1H candle closes below BB     |
| Exit               | Price closes through 20 SMA   |
| Stop loss          | ATR(14) × 2.0 from entry      |
| Take profit        | Stop distance × 2.0 (min 2:1)|
| Risk per trade     | 1% of account balance         |
| Max signals/day    | 2                             |
| Leverage           | 1× (risk managed by sizing)   |

### 5 Filters
1. **Body filter** — candle body ≥ 40% of total range (rejects wick spikes)
2. **Funding filter** — skip ±30 min around 00:00 / 08:00 / 16:00 UTC
3. **BB squeeze** — skip when band width < 1.5 × ATR
4. **Daily bias** — only LONG above daily 20 SMA, only SHORT below it
5. **Signal windows** — S1: 13–16 UTC | S2: 18–20 UTC

---

## Safety checklist before going live

- [ ] Tested on Binance Futures Testnet for at least 2 weeks
- [ ] API key has IP whitelist set (your server IP only)
- [ ] API key has NO withdrawal permissions
- [ ] `TESTNET=false` only set when ready
- [ ] Bot starts with small balance ($100–$200) before scaling
- [ ] You understand this is a risk — never trade money you can't afford to lose

---

## Disclaimer

This software is for educational purposes. Cryptocurrency trading involves
substantial risk of loss. Past backtest performance does not guarantee future
results. You are solely responsible for your trading decisions.
