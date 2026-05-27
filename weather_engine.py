# -*- coding: utf-8 -*-
"""
weather_engine.py
Standalone India weather prediction engine using climatological baselines.
No large IMD downloads needed — uses Open-Meteo historical archive API.
"""

import numpy as np
import pandas as pd
import requests
import json
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# ── City definitions ──────────────────────────────────────────────────────────
CITIES = {
    'Delhi'    : {'lat': 28.6,  'lon': 77.2,  'emoji': '🏛️'},
    'Mumbai'   : {'lat': 19.1,  'lon': 72.9,  'emoji': '🌊'},
    'Chennai'  : {'lat': 13.1,  'lon': 80.3,  'emoji': '🌴'},
    'Kolkata'  : {'lat': 22.6,  'lon': 88.4,  'emoji': '🎭'},
    'Hyderabad': {'lat': 17.4,  'lon': 78.5,  'emoji': '💎'},
    'Bhopal'   : {'lat': 23.3,  'lon': 77.4,  'emoji': '🏞️'},
    'Ahmedabad': {'lat': 23.0,  'lon': 72.6,  'emoji': '🪁'},
    'Bengaluru': {'lat': 12.9,  'lon': 77.6,  'emoji': '💻'},
}

RAIN_LABELS = [
    ('No rain',        '☀️',  '#f59e0b'),
    ('Light rain',     '🌦️', '#60a5fa'),
    ('Moderate rain',  '🌧️', '#3b82f6'),
    ('Rather heavy',   '🌧️', '#2563eb'),
    ('Heavy rain',     '⛈️', '#1d4ed8'),
    ('Very heavy',     '⛈️', '#1e3a8a'),
    ('Extremely heavy','🌊', '#0f172a'),
]
RAIN_BINS = [-1, 2.4, 7.5, 35.4, 64.4, 115.5, 204.4, 9999]


def fetch_recent_weather(city: str, days_back: int = 16) -> pd.DataFrame:
    """
    Pull recent + forecast data from Open-Meteo for the given city.
    Returns a DataFrame with columns: date, tmax, tmin, rain
    """
    meta = CITIES[city]
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


def fetch_historical_climatology(city: str, years: int = 10) -> pd.DataFrame:
    """
    Fetch historical daily data from Open-Meteo Archive to build climatology.
    Caches result to avoid repeat calls.
    """
    import os, pickle
    cache_path = f"models/{city}_clim.pkl"
    os.makedirs("models", exist_ok=True)

    if os.path.exists(cache_path):
        with open(cache_path, 'rb') as f:
            return pickle.load(f)

    meta = CITIES[city]
    end_year   = datetime.utcnow().year - 1
    start_year = end_year - years + 1
    all_dfs = []

    for yr in range(start_year, end_year + 1):
        url = (
            "https://archive-api.open-meteo.com/v1/archive"
            f"?latitude={meta['lat']}&longitude={meta['lon']}"
            f"&start_date={yr}-01-01&end_date={yr}-12-31"
            "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum"
            "&timezone=Asia%2FKolkata"
        )
        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            d = resp.json()['daily']
            df = pd.DataFrame({
                'date': pd.to_datetime(d['time']),
                'tmax': d['temperature_2m_max'],
                'tmin': d['temperature_2m_min'],
                'rain': d['precipitation_sum'],
            })
            all_dfs.append(df)
        except Exception as e:
            print(f"  Warning: could not fetch {yr} for {city}: {e}")

    if not all_dfs:
        return pd.DataFrame()

    combined = pd.concat(all_dfs, ignore_index=True)
    combined['rain'] = combined['rain'].fillna(0.0)
    combined['tmax'] = combined['tmax'].ffill().bfill()
    combined['tmin'] = combined['tmin'].ffill().bfill()
    combined['doy']  = combined['date'].dt.dayofyear

    with open(cache_path, 'wb') as f:
        pickle.dump(combined, f)

    return combined


def predict_city(city: str, target_date: datetime = None) -> dict:
    """
    Main prediction function for a single city.
    Returns a dict with forecast and climatology info.
    """
    if target_date is None:
        target_date = datetime.utcnow().date() + timedelta(days=1)
    target_ts = pd.Timestamp(target_date)

    # Fetch recent data (past 16 days + 7-day forecast from Open-Meteo)
    recent_df = fetch_recent_weather(city, days_back=16)

    # Check if Open-Meteo already has the target date in its forecast
    forecast_row = recent_df[recent_df['date'].dt.date == target_ts.date()]
    if not forecast_row.empty:
        tmax = float(forecast_row['tmax'].iloc[0])
        tmin = float(forecast_row['tmin'].iloc[0])
        rain = max(0.0, float(forecast_row['rain'].iloc[0]))
        source = "Open-Meteo NWP forecast"
    else:
        # Fall back to climatology-based estimate
        hist = fetch_historical_climatology(city)
        doy = target_ts.dayofyear
        window = hist[hist['doy'].between(max(1, doy - 10), min(365, doy + 10))]
        tmax = float(window['tmax'].mean())
        tmin = float(window['tmin'].mean())
        rain = float(window['rain'].mean())
        source = "Climatological normal"

    # Heatwave logic (IMD criteria)
    # Fetch climatology for anomaly calc
    hist = fetch_historical_climatology(city)
    doy_target = target_ts.dayofyear
    clim_window = hist[hist['doy'].between(max(1, doy_target - 10), min(365, doy_target + 10))]
    clim_tmax = float(clim_window['tmax'].mean()) if len(clim_window) else tmax
    clim_tmin = float(clim_window['tmin'].mean()) if len(clim_window) else tmin
    clim_rain = float(clim_window['rain'].mean()) if len(clim_window) else rain

    tmax_anom = tmax - clim_tmax
    hw_abs    = tmax >= 40.0
    hw_anom   = tmax_anom >= 4.5
    hw_flag   = hw_abs or hw_anom

    # Rainfall category
    cat_idx = pd.cut([rain], bins=RAIN_BINS, labels=False)[0]
    if pd.isna(cat_idx):
        cat_idx = 0
    rain_label = RAIN_LABELS[int(cat_idx)]

    # Recent trend (last 3 days vs previous 3 days in history)
    hist3 = recent_df[recent_df['date'].dt.date < target_ts.date()].tail(3)
    trend_tmax = "rising" if hist3['tmax'].is_monotonic_increasing else (
                 "falling" if hist3['tmax'].is_monotonic_decreasing else "stable")

    return {
        'city'       : city,
        'emoji'      : CITIES[city]['emoji'],
        'date'       : str(target_ts.date()),
        'tmax'       : round(tmax, 1),
        'tmin'       : round(tmin, 1),
        'rain'       : round(rain, 1),
        'clim_tmax'  : round(clim_tmax, 1),
        'clim_tmin'  : round(clim_tmin, 1),
        'clim_rain'  : round(clim_rain, 1),
        'tmax_anom'  : round(tmax_anom, 1),
        'hw_flag'    : hw_flag,
        'rain_label' : rain_label,
        'trend_tmax' : trend_tmax,
        'source'     : source,
    }


def run_all_cities(target_date=None) -> list:
    """Run predictions for all 8 cities."""
    results = []
    for city in CITIES:
        print(f"  ▸ Predicting {city}...")
        try:
            r = predict_city(city, target_date)
            results.append(r)
        except Exception as e:
            print(f"    ❌ Failed for {city}: {e}")
    return results


if __name__ == "__main__":
    from datetime import date
    tomorrow = date.today() + timedelta(days=1)
    print(f"\n🌦️ Running predictions for {tomorrow}\n")
    results = run_all_cities(tomorrow)
    for r in results:
        print(f"\n{r['emoji']} {r['city']}: Tmax={r['tmax']}°C, Tmin={r['tmin']}°C, Rain={r['rain']}mm {r['rain_label'][1]}")
        if r['hw_flag']:
            print(f"  ⚠️  HEATWAVE ALERT")
