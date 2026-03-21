"""
Caching Flow Example: Weather API with Memoization

This example demonstrates task caching to avoid redundant API calls.
The first request for a city fetches weather data; subsequent requests
for the same city return the cached result instantly.
"""

from water.core import Flow, create_task
from water.resilience import InMemoryCache
from pydantic import BaseModel
from typing import Dict, Any
import asyncio
import random

# Data schemas
class WeatherRequest(BaseModel):
    city: str

class WeatherResult(BaseModel):
    city: str
    temperature: float
    condition: str
    cached: bool

class ForecastResult(BaseModel):
    city: str
    temperature: float
    condition: str
    forecast: str

# Shared cache — persists across multiple flow runs
weather_cache = InMemoryCache()

# Simulated API call counter
api_calls = 0

# Step 1: Fetch weather data (cached)
def fetch_weather(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Simulate an expensive weather API call."""
    global api_calls
    api_calls += 1

    city = params["input_data"]["city"]

    # Simulate API response
    temperature = round(random.uniform(15, 35), 1)
    conditions = ["sunny", "cloudy", "rainy", "windy"]
    condition = random.choice(conditions)

    print(f"  [API CALL #{api_calls}] Fetched weather for {city}: {temperature}°C, {condition}")

    return {
        "city": city,
        "temperature": temperature,
        "condition": condition,
        "cached": False,
    }

# Step 2: Generate forecast (not cached — runs every time)
def generate_forecast(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Generate a simple forecast based on current weather."""
    data = params["input_data"]

    if data["temperature"] > 30:
        forecast = "Hot day ahead — stay hydrated!"
    elif data["temperature"] > 20:
        forecast = "Pleasant weather expected."
    else:
        forecast = "Cool temperatures — bring a jacket."

    return {
        "city": data["city"],
        "temperature": data["temperature"],
        "condition": data["condition"],
        "forecast": forecast,
    }

# Create tasks
weather_task = create_task(
    id="fetch_weather",
    description="Fetch current weather from API",
    input_schema=WeatherRequest,
    output_schema=WeatherResult,
    execute=fetch_weather,
    cache=weather_cache,  # Enable caching for this task
)

forecast_task = create_task(
    id="generate_forecast",
    description="Generate forecast from weather data",
    input_schema=WeatherResult,
    output_schema=ForecastResult,
    execute=generate_forecast,
    # No cache — always generates fresh forecast text
)

# Build the flow
weather_flow = Flow(id="weather_lookup", description="Cached weather lookup with forecast")
weather_flow.then(weather_task).then(forecast_task).register()

async def main():
    """Demonstrate caching by looking up the same city multiple times."""

    cities = ["London", "Tokyo", "London", "Paris", "Tokyo", "London"]

    print("=== Weather Lookup with Caching ===\n")

    for city in cities:
        print(f"Looking up weather for {city}...")
        result = await weather_flow.run({"city": city})
        print(f"  Result: {result['city']} — {result['temperature']}°C, "
              f"{result['condition']}, {result['forecast']}")
        print()

    print(f"Total API calls made: {api_calls}")
    print(f"Total lookups: {len(cities)}")
    print(f"Cache saved {len(cities) - api_calls} API calls!")

if __name__ == "__main__":
    asyncio.run(main())
