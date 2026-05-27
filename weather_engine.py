# -*- coding: utf-8 -*-
"""
weather_engine.py
Standalone India weather prediction engine using climatological baselines.
No large IMD downloads needed — uses Open-Meteo historical archive API.

FIXES applied:
  - fetch_historical_climatology: ONE API call per city (not 10 year-by-year calls)
  - predict_city: climatology fetched only ONCE per city (not twice)
  - Cities: Bengaluru, Delhi, Kolkata, Chennai, Mumbai only
"""

import os
import pickle
import numpy as np
import pandas as pd
import requests
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')


# ── City definitions (5 cities, Bengaluru first) ──────────────────────────────
CITIES = {
    'Bengaluru': {'lat': 12.9,  'lon': 77.6,  'emoji': '💻'},
    'Delhi'    : {'lat': 28.6,  'lon': 77.2,  'emoji': '🏛️'},
    'Kolkata'  : {'lat': 22.6,  'lon': 88.4,  'emoji': '🎭'},
    'Chennai'  : {'lat': 13.1,  'lon': 80.3,  'emoji': '🌴'},
    'Mumbai'   : {'lat': 19.1,  'lon': 72.9,  'emoji': '🌊'},
}

RAIN_LABELS = [
    ('No rain',         '☀️',  '#f59e0b'),
    ('Light rain',      '🌦️', '#60a5fa'),
    ('Moderate rain',   '🌧️', '#3b82f6'),
    ('Rather heavy',    '🌧️', '#2563eb'),
    ('Heavy rain',      '⛈️', '#1d4ed8'),
    ('Very heavy',      '⛈️', '#1e3a8a'),
    ('Extremely heavy', '🌊', '#0f172a'),
]
RAIN_BINS = [-1, 2.4, 7.5, 35.4, 64.4, 115.5, 204.4, 9999]


# ── Fetch recent + forecast weather ──────────────────────────────────────────
def fetch_recent_weather(city: str, days_back: int = 16) -> pd.DataFrame:
    meta       = CITIES[city]
    end_date   = datetime.utcnow().date()
    start_date = end_date - timedelta(days=days_back)

    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={meta['lat']}&longitude={meta['lon']}"
        f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum"
        f"&start_date={start_date}&end_date={end_date + timedelta(days=7)}"
        "&timezone=Asia%2FKolkata"
    )
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    d = resp.json()['daily']

    df = pd.DataFrame({
        'date': pd.to_datetime(d['time']),
        'tmax': d['temperature_2m_max'],
        'tmin': d['temperature_2m_min'],
        'rain': d['precipitation_sum'],
    })
    df['rain'] = df['rain'].fillna(0.0)
    df['tmax'] = df['tmax'].ffill().bfill()
    df['tmin'] = df['tmin'].ffill().bfill()
    return df.reset_index(drop=True)


# ── Fetch historical climatology (ONE API call, cached) ───────────────────────
def fetch_historical_climatology(city: str, years: int = 10) -> pd.DataFrame:
    cache_path = f"models/{city}_clim.pkl"
    os.makedirs("models", exist_ok=True)

    if os.path.exists(cache_path):
        print(f"    ✅ Cache hit for {city}")
        with open(cache_path, 'rb') as f:
            return pickle.load(f)

    meta       = CITIES[city]
    end_year   = datetime.utcnow().year - 1
    start_year = end_year - years + 1

    print(f"    📡 Fetching {years}yr climatology for {city} (single API call)...")
    url = (
        "https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={meta['lat']}&longitude={meta['lon']}"
        f"&start_date={start_year}-01-01&end_date={end_year}-12-31"
        "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum"
        "&timezone=Asia%2FKolkata"
    )
    try:
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        d = resp.json()['daily']
        combined = pd.DataFrame({
            'date': pd.to_datetime(d['time']),
            'tmax': d['temperature_2m_max'],
            'tmin': d['temperature_2m_min'],
            'rain': d['precipitation_sum'],
        })
    except Exception as e:
        print(f"    ❌ Climatology fetch failed for {city}: {e}")
        return pd.DataFrame()

    combined['rain'] = combined['rain'].fillna(0.0)
    combined['tmax'] = combined['tmax'].ffill().bfill()
    combined['tmin'] = combined['tmin'].ffill().bfill()
    combined['doy']  = combined['date'].dt.dayofyear

    with open(cache_path, 'wb') as f:
        pickle.dump(combined, f)
    print(f"    💾 Cached climatology for {city}")

    return combined


# ── Predict a single city ─────────────────────────────────────────────────────
def predict_city(city: str, target_date=None) -> dict:
    if target_date is None:
        target_date = datetime.utcnow().date() + timedelta(days=1)
    target_ts = pd.Timestamp(target_date)

    # Fetch climatology ONCE
    hist       = fetch_historical_climatology(city)
    doy_target = target_ts.dayofyear

    if not hist.empty:
        clim_window = hist[hist['doy'].between(
            max(1, doy_target - 10),
            min(365, doy_target + 10)
        )]
        clim_tmax = float(clim_window['tmax'].mean()) if not clim_window.empty else 30.0
        clim_tmin = float(clim_window['tmin'].mean()) if not clim_window.empty else 20.0
        clim_rain = float(clim_window['rain'].mean()) if not clim_window.empty else 0.0
    else:
        clim_tmax, clim_tmin, clim_rain = 30.0, 20.0, 0.0

    # Fetch recent + NWP forecast
    recent_df    = fetch_recent_weather(city, days_back=16)
    forecast_row = recent_df[recent_df['date'].dt.date == target_ts.date()]

    if not forecast_row.empty:
        tmax   = float(forecast_row['tmax'].iloc[0])
        tmin   = float(forecast_row['tmin'].iloc[0])
        rain   = max(0.0, float(forecast_row['rain'].iloc[0]))
        source = "Open-Meteo NWP forecast"
    else:
        tmax, tmin, rain = clim_tmax, clim_tmin, clim_rain
        source = "Climatological normal"

    # Heatwave logic (IMD criteria)
    tmax_anom = tmax - clim_tmax
    hw_flag   = (tmax >= 40.0) or (tmax_anom >= 4.5)

    # Rainfall category
    cat_idx = pd.cut([rain], bins=RAIN_BINS, labels=False)[0]
    if pd.isna(cat_idx):
        cat_idx = 0
    rain_label = RAIN_LABELS[int(cat_idx)]

    # Recent trend
    hist3      = recent_df[recent_df['date'].dt.date < target_ts.date()].tail(3)
    trend_tmax = (
        "rising"  if hist3['tmax'].is_monotonic_increasing else
        "falling" if hist3['tmax'].is_monotonic_decreasing else
        "stable"
    )

    return {
        'city'      : city,
        'emoji'     : CITIES[city]['emoji'],
        'date'      : str(target_ts.date()),
        'tmax'      : round(tmax, 1),
        'tmin'      : round(tmin, 1),
        'rain'      : round(rain, 1),
        'clim_tmax' : round(clim_tmax, 1),
        'clim_tmin' : round(clim_tmin, 1),
        'clim_rain' : round(clim_rain, 1),
        'tmax_anom' : round(tmax_anom, 1),
        'hw_flag'   : hw_flag,
        'rain_label': rain_label,
        'trend_tmax': trend_tmax,
        'source'    : source,
    }


# ── Run all cities ────────────────────────────────────────────────────────────
def run_all_cities(target_date=None) -> list:
    """Run predictions for all 5 cities."""
    results = []
    for city in CITIES:
        print(f"  ▸ Predicting {city}...")
        try:
            r = predict_city(city, target_date)
            results.append(r)
            print(f"    ✅ {city}: Tmax={r['tmax']}°C  Tmin={r['tmin']}°C  "
                  f"Rain={r['rain']}mm  {'⚠️ HEATWAVE' if r['hw_flag'] else ''}")
        except Exception as e:
            print(f"    ❌ Failed for {city}: {e}")
    return results


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    from datetime import date
    tomorrow = date.today() + timedelta(days=1)
    print(f"\n🌦️ Running predictions for {tomorrow}\n")
    results = run_all_cities(tomorrow)
    print("\n── Summary ──────────────────────────────────────────")
    for r in results:
        print(f"{r['emoji']} {r['city']:<12} "
              f"Tmax={r['tmax']}°C  Tmin={r['tmin']}°C  "
              f"Rain={r['rain']}mm  {r['rain_label'][1]}"
              f"{'  ⚠️ HEATWAVE' if r['hw_flag'] else ''}")
