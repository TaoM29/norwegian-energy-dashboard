
# weather.py
import pandas as pd, requests, streamlit as st

AREA_COORDS = {
    "NO1": (59.9139, 10.7522),  # Oslo
    "NO2": (58.1467, 7.9956),   # Kristiansand
    "NO3": (63.4305, 10.3951),  # Trondheim
    "NO4": (69.6492, 18.9553),  # Tromsø
    "NO5": (60.3913, 5.3221),   # Bergen
}

@st.cache_data(show_spinner=True, ttl=6*3600)
def load_openmeteo_era5(area: str, year: int, timezone: str = "Europe/Oslo") -> pd.DataFrame:
    lat, lon = AREA_COORDS[area]
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": f"{year}-01-01", "end_date": f"{year}-12-31",
        "hourly": ["temperature_2m","precipitation","windspeed_10m","windgusts_10m","winddirection_10m"],
        "timezone": timezone,
    }
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    h = r.json().get("hourly", {})
    df = pd.DataFrame({
        "time": pd.to_datetime(h.get("time", [])),
        "temperature_2m (°C)": h.get("temperature_2m", []),
        "precipitation (mm)": h.get("precipitation", []),
        "wind_speed_10m (m/s)": h.get("windspeed_10m", []),
        "wind_gusts_10m (m/s)": h.get("windgusts_10m", []),
        "wind_direction_10m (°)": h.get("winddirection_10m", []),
    })
    return df.sort_values("time").reset_index(drop=True)
