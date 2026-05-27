# -*- coding: utf-8 -*-
"""
agent.py
Agentic layer: calls Groq API (llama-3.3-70b) to generate a natural-language
weather briefing, then formats it into a rich HTML email and sends via Gmail SMTP.
"""

import os
import json
import smtplib
import requests
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta, date


# ── Config ────────────────────────────────────────────────────────────────────
RECIPIENT_EMAIL = "joyghoshin@gmail.com"
SENDER_EMAIL    = os.environ.get("GMAIL_SENDER")          # set in GitHub Secrets
GMAIL_APP_PASS  = os.environ.get("GMAIL_APP_PASSWORD")    # set in GitHub Secrets
GROQ_API_KEY    = os.environ.get("GROQ_API_KEY")          # set in GitHub Secrets


# ── Groq agent: generate narrative ───────────────────────────────────────────
def generate_narrative(results: list, target_date: str) -> str:
    """
    Call Groq (llama-3.3-70b-versatile) to write a human-friendly weather briefing.
    Groq is free-tier friendly and extremely fast (~1-2s).
    """
    summary_json = json.dumps(results, indent=2)

    prompt = f"""You are an expert Indian meteorologist writing a daily weather briefing email.
Today's date is {date.today().isoformat()}. The forecast is for {target_date}.

Here is the model output for 8 Indian cities:
{summary_json}

Write a concise but engaging 200-250 word weather briefing covering:
1. A one-line overall summary of conditions across India
2. Notable cities — highlight extremes (hottest, coolest, wettest, any heatwave alerts)
3. Any active heatwave alerts with practical safety advice
4. A short outlook line

Use a professional but friendly tone. Use city emojis naturally.
Do NOT repeat raw numbers — synthesize them into narrative.
Return ONLY the narrative text, no JSON, no markdown headers."""

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": "llama-3.3-70b-versatile",
        "max_tokens": 600,
        "temperature": 0.7,
        "messages": [
            {"role": "system", "content": "You are an expert Indian meteorologist. Write clear, engaging weather briefings."},
            {"role": "user", "content": prompt},
        ],
    }
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers=headers, json=body, timeout=60
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


# ── HTML email builder ────────────────────────────────────────────────────────
def build_html_email(results: list, narrative: str, target_date: str) -> str:
    heatwave_cities = [r for r in results if r.get('hw_flag')]
    alert_banner = ""
    if heatwave_cities:
        cities_str = ", ".join(f"{r['emoji']} {r['city']}" for r in heatwave_cities)
        alert_banner = f"""
        <div style="background:#fee2e2;border-left:5px solid #dc2626;padding:14px 20px;margin-bottom:20px;border-radius:6px;">
          <strong style="color:#dc2626;">⚠️ HEATWAVE ALERT:</strong>
          <span style="color:#7f1d1d;"> {cities_str}</span>
        </div>"""

    # City cards
    cards_html = ""
    for r in results:
        anom_color = "#dc2626" if r['tmax_anom'] > 3 else ("#16a34a" if r['tmax_anom'] < -2 else "#374151")
        anom_sign  = "+" if r['tmax_anom'] >= 0 else ""
        hw_badge   = '<span style="background:#fee2e2;color:#dc2626;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:700;margin-left:8px;">⚠️ HEATWAVE</span>' if r['hw_flag'] else ""
        rain_icon  = r['rain_label'][1]
        rain_name  = r['rain_label'][0]

        cards_html += f"""
        <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;padding:16px 20px;margin-bottom:12px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <span style="font-size:17px;font-weight:700;color:#111827;">{r['emoji']} {r['city']}</span>
            {hw_badge}
            <span style="font-size:13px;color:#6b7280;">{rain_icon} {rain_name}</span>
          </div>
          <div style="display:flex;gap:24px;flex-wrap:wrap;">
            <div>
              <span style="font-size:13px;color:#6b7280;">Max Temp</span><br>
              <span style="font-size:22px;font-weight:700;color:#dc2626;">{r['tmax']}°C</span>
              <span style="font-size:12px;color:{anom_color};"> ({anom_sign}{r['tmax_anom']}°C vs normal)</span>
            </div>
            <div>
              <span style="font-size:13px;color:#6b7280;">Min Temp</span><br>
              <span style="font-size:22px;font-weight:700;color:#2563eb;">{r['tmin']}°C</span>
              <span style="font-size:12px;color:#6b7280;"> (normal {r['clim_tmin']}°C)</span>
            </div>
            <div>
              <span style="font-size:13px;color:#6b7280;">Rainfall</span><br>
              <span style="font-size:22px;font-weight:700;color:#0369a1;">{r['rain']} mm</span>
              <span style="font-size:12px;color:#6b7280;"> (normal {r['clim_rain']} mm)</span>
            </div>
            <div>
              <span style="font-size:13px;color:#6b7280;">Trend</span><br>
              <span style="font-size:14px;color:#374151;">
                {"📈" if r['trend_tmax']=='rising' else "📉" if r['trend_tmax']=='falling' else "➡️"} {r['trend_tmax'].title()}
              </span>
            </div>
          </div>
        </div>"""

    narrative_html = narrative.replace('\n', '<br>')

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <div style="max-width:680px;margin:32px auto;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">

    <!-- Header -->
    <div style="background:linear-gradient(135deg,#1d4ed8 0%,#0369a1 100%);padding:32px 36px;text-align:center;">
      <div style="font-size:36px;margin-bottom:8px;">🌦️</div>
      <h1 style="margin:0;color:#ffffff;font-size:24px;font-weight:700;letter-spacing:-0.5px;">
        India Weather Briefing
      </h1>
      <p style="margin:8px 0 0;color:#bfdbfe;font-size:15px;">
        Forecast for {target_date} · Generated {datetime.utcnow().strftime('%H:%M UTC')}
      </p>
    </div>

    <!-- Body -->
    <div style="padding:28px 36px;">
      {alert_banner}

      <!-- AI Narrative -->
      <div style="background:#eff6ff;border-left:4px solid #3b82f6;padding:16px 20px;margin-bottom:28px;border-radius:6px;">
        <p style="margin:0;font-size:15px;line-height:1.7;color:#1e3a8a;">
          🤖 <strong>AI Briefing</strong><br><br>
          {narrative_html}
        </p>
      </div>

      <!-- City Cards -->
      <h2 style="font-size:16px;font-weight:700;color:#374151;margin:0 0 14px;">
        📍 City-by-City Forecast
      </h2>
      {cards_html}

      <!-- Footer note -->
      <p style="margin-top:24px;font-size:12px;color:#9ca3af;text-align:center;">
        Data: Open-Meteo NWP · Heatwave criteria: IMD (Tmax ≥ 40°C or anomaly ≥ +4.5°C)<br>
        Powered by Groq LLaMA-3.3-70b Agent + GitHub Actions · Sent to {RECIPIENT_EMAIL}
      </p>
    </div>
  </div>
</body>
</html>"""


# ── Send email ────────────────────────────────────────────────────────────────
def send_email(html_body: str, subject: str):
    if not SENDER_EMAIL or not GMAIL_APP_PASS:
        raise EnvironmentError(
            "GMAIL_SENDER and GMAIL_APP_PASSWORD must be set as environment variables / GitHub Secrets."
        )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = RECIPIENT_EMAIL
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SENDER_EMAIL, GMAIL_APP_PASS)
        server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())

    print(f"✅ Email sent to {RECIPIENT_EMAIL}")


# ── Main entry point ──────────────────────────────────────────────────────────
def run_agent():
    from weather_engine import run_all_cities

    target_date = str(date.today() + timedelta(days=1))
    print(f"\n🤖 India Weather Agent starting — forecasting for {target_date}\n")

    print("📡 Fetching weather predictions for all cities...")
    results = run_all_cities(target_date)

    if not results:
        print("❌ No results returned. Aborting.")
        return

    print("\n✍️  Generating AI narrative via Claude...")
    narrative = generate_narrative(results, target_date)
    print(f"\n--- Narrative ---\n{narrative}\n---\n")

    print("📧 Building and sending email...")
    html = build_html_email(results, narrative, target_date)

    hw_count = sum(1 for r in results if r.get('hw_flag'))
    hw_suffix = f" ⚠️ {hw_count} HEATWAVE ALERT{'S' if hw_count>1 else ''}" if hw_count else ""
    subject = f"🌦️ India Weather Briefing — {target_date}{hw_suffix}"

    send_email(html, subject)
    print("\n✅ Agent run complete.")


if __name__ == "__main__":
    run_agent()
