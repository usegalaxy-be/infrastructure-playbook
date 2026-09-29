import requests


def get_carbon_intensity(auth_token, lat, lon) -> float:
    request = (
            f"https://api.electricitymaps.com/v3/carbon-intensity/"
            f"latest?lat={lat}&lon={lon}&temporalGranularity=hourly"
            )

    response = requests.get(
        request,
        headers={ "auth-token": auth_token }
    ).json()
    return { "carbon_intensity": response["carbonIntensity"] }


def get_price_day_ahead(auth_token, lat, lon) -> dict:
    request = (
            f"https://api.electricitymaps.com/v3/price-day-ahead/"
            f"latest?lat={lat}&lon={lon}&temporalGranularity=hourly"
            )

    response = requests.get(
        request,
        headers={ "auth-token": auth_token }
    ).json()
    # todo: unit conversions if needed
    return { "price_day_ahead": response["value"] }


def get_electricity_mix(auth_token, lat, lon) -> dict:
    request = (
            f"https://api.electricitymaps.com/v3/electricity-mix/"
            f"latest?lat={lat}&lon={lon}&temporalGranularity=hourly"
            )
    
    response = requests.get(
        request,
        headers={ "auth-token": auth_token }
    ).json()
    # todo: unit conversions if needed
    mix = response["data"][0]["mix"]
    return mix


def get_energy_metrics(energy_auth_token, destinations) -> dict:
    """
    Retrieve carbon intensity data for each pulsar node.
    """
    energy_metrics = {}

    for node, coords in destinations.items():
        lat = coords["latitude"]
        lon = coords["longitude"]

        carbon_intensity = get_carbon_intensity(energy_auth_token, lat, lon)
        price_day_ahead = get_price_day_ahead(energy_auth_token, lat, lon)
        electricity_mix = get_electricity_mix(energy_auth_token, lat, lon)
        energy_metrics[node] = {**carbon_intensity, **price_day_ahead, **electricity_mix}


    return energy_metrics

