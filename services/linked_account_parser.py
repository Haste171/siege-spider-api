import requests
import os
from dotenv import load_dotenv

load_dotenv()

class LinkedAccountParser:
    def __init__(self):
        pass

    @staticmethod
    def resolve_steam_vanity_url(vanity_url: str):
        response = requests.get(
            "https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/",
            params={
                "key": os.getenv("STEAM_WEB_API_KEY"),
                "vanityurl": vanity_url
            }
        )
        data = response.json()

        if data.get("response").get("success") == 1:
            return data.get("response").get("steamid")
        elif data.get("response").get("success") == 42:
            # probably not a vanity url if it gets this status code
            return vanity_url
        else:
            return None
