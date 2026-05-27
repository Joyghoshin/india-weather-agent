# 🌦️ India Weather Agent

> **Agentic daily weather briefing** — 8 Indian cities, AI-written narrative, delivered to your inbox every morning at 5:30 AM IST via GitHub Actions.

---

## 🏗️ Architecture

```
GitHub Actions (cron: 5:30 AM IST)
        │
        ▼
weather_engine.py ──► Open-Meteo API (free, no key needed)
        │               ↳ Real NWP forecast (tmax, tmin, rain)
        │               ↳ Historical climatology (heatwave baseline)
        ▼
   agent.py ──────────► Groq API / LLaMA-3.3-70b (writes human narrative)
        │
        ▼
   Gmail SMTP ─────────► joyghoshin@gmail.com
```

**No IMD binary downloads. No large datasets. Runs in < 3 minutes.**

---

## 📬 What You Get Every Morning

A rich HTML email containing:
- **⚠️ Heatwave alert banner** (if any city triggers IMD criteria)
- **🤖 AI-written 200-word briefing** synthesized by Claude
- **📍 City cards** for all 8 cities: Tmax, Tmin, Rainfall, anomaly vs normal, trend
- Cities covered: Delhi, Mumbai, Chennai, Kolkata, Hyderabad, Bhopal, Ahmedabad, Bengaluru

---

## 🚀 Setup (5 minutes)

### Step 1 — Fork / Clone this repo

```bash
git clone https://github.com/YOUR_USERNAME/india-weather-agent
cd india-weather-agent
```

### Step 2 — Get your secrets ready

You need **3 secrets**:

| Secret | How to get it |
|--------|--------------|
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) → API Keys (free account) |
| `GMAIL_SENDER` | Your Gmail address (e.g. `you@gmail.com`) |
| `GMAIL_APP_PASSWORD` | **Not your Gmail password.** See below ↓ |

#### Getting a Gmail App Password
1. Go to [myaccount.google.com/security](https://myaccount.google.com/security)
2. Enable **2-Step Verification** (required)
3. Search "App passwords" → Create one named "Weather Agent"
4. Copy the 16-character password → use as `GMAIL_APP_PASSWORD`

### Step 3 — Add secrets to GitHub

In your repo: **Settings → Secrets and variables → Actions → New repository secret**

Add all 3 secrets listed above.

### Step 4 — Enable Actions

Go to **Actions tab** → click **"I understand my workflows, go ahead and enable them"**

### Step 5 — Test it manually

**Actions tab → "India Weather Agent" → "Run workflow"** → click the green button.

Check your inbox within ~3 minutes! 📬

---

## ⏰ Schedule

Runs automatically at **`0 0 * * *` UTC = 5:30 AM IST** every day.

To change the time, edit `.github/workflows/daily_weather.yml`:
```yaml
- cron: '0 0 * * *'   # Change this line
```
UTC to IST = UTC + 5:30. So for 6:00 AM IST → use `30 0 * * *`.

---

## 🔧 Local Development

```bash
pip install -r requirements.txt

# Set env vars
export ANTHROPIC_API_KEY="sk-ant-..."
export GMAIL_SENDER="you@gmail.com"
export GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx"

# Run the agent
python agent.py

# Or just test predictions (no email)
python weather_engine.py
```

---

## 📦 Files

```
india-weather-agent/
├── weather_engine.py       # Prediction engine (Open-Meteo API + climatology)
├── agent.py                # Agentic layer: Claude API + email builder + SMTP
├── requirements.txt        # Python deps (minimal — no heavy ML libraries)
├── .github/
│   └── workflows/
│       └── daily_weather.yml   # GitHub Actions cron job
└── models/                 # Auto-created: cached climatology files
```

---

## 🌡️ Heatwave Criteria (IMD Standard)

A day is flagged as a heatwave if:
- **Absolute**: Tmax ≥ 40°C, **OR**
- **Anomaly**: Tmax is ≥ 4.5°C above the 10-year climatological normal for that day of year

---

## 📡 Data Sources

- **Forecasts**: [Open-Meteo](https://open-meteo.com/) — free, no API key, global NWP
- **Climatology**: Open-Meteo Archive API — 10-year historical baseline, cached locally
- **AI narrative**: Groq API (`llama-3.3-70b-versatile`) — free tier, ~1-2s response

---

## 🛠️ Troubleshooting

| Problem | Fix |
|---------|-----|
| Email not received | Check GitHub Actions logs; verify Gmail App Password |
| `GMAIL_APP_PASSWORD` error | 2FA must be enabled; use App Password, not regular password |
| `GROQ_API_KEY` error | Verify key at console.groq.com; check you copied it fully |
| Open-Meteo timeout | GitHub will retry on next day's schedule |
| Cron not running | GitHub disables workflows after 60 days of no repo activity — push a commit |

---

## 📝 License

MIT
