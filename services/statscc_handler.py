import os
from dotenv import load_dotenv
import requests

load_dotenv()

class StatsCCHandler:
    def __init__(self):
        api_key = os.getenv('STATSCC_API_KEY')
        self.base_url = "https://r6.statsapi.net"
        self.headers = {
            "x-api-key": api_key,
            # "User-Agent": "siege-spider"
        }

    def cache_mechanism(self):
        # TODO: "We recommend keeping a local cache, and updating it every 5 minutes for quick access."
        # this needs to be on a global scale inheriting from requests library and overwriting it with redis cache access.
        pass

    def fetch_by_profile_id(self, profile_id: str):
        """
        Fetch profile by id
        GET https://r6.statsapi.net/profiles/{profile_id}

        :param profile_id:
        :return:
        """
        url = f"{self.base_url}/profiles/{profile_id}"
        r = requests.get(url, headers=self.headers)
        if r.status_code == 200:
            if r.json().get('statusCode') == 404:
                return {}
            return r.json()
        else:
            raise RuntimeError(f"Failed to run request (URL: {url})), response code: {r.status_code}\n\n{r.text}")

    def fetch_profile_by_username(self, username: str, platform: str = ["uplay"]):
        """
        Fetch profile by exact username on a platform
        GET https://r6.statsapi.net/profiles/lookup?displayName={username}&platform={platform}

        :param username:
        :param platform:
                valid platforms are 'uplay', 'xbl', 'psn'
        :return:
        """
        url = f"{self.base_url}/profiles/lookup?displayName={username}&platform={platform}"
        r = requests.get(url, headers=self.headers)
        if r.status_code == 200:
            return r.json()
        else:
            raise RuntimeError(f"Failed to run request (URL: {url})), response code: {r.status_code}\n\n{r.text}")

    def fetch_config(self):
        """
        Config
        Fetch all the common data that all the other endpoints reference from. For example, rank in a response will reference response.ranks[rank] which gives you the display name.

        GET https://r6.statsapi.net/v1/config

        :return:
        """
        url = f"{self.base_url}/v1/config"
        r = requests.get(url,  headers=self.headers)
        if r.status_code == 200:
            return r.json()
        else:
            raise RuntimeError(f"Failed to run request (URL: {url})), response code: {r.status_code}\n\n{r.text}")

def main():
    statscc_handler = StatsCCHandler()

    # fetch_by_username = statscc_handler.fetch_profile_by_username("Ext", platform="uplay")
    # print(fetch_by_username)

    fetch_by_profile_id = statscc_handler.fetch_by_profile_id("6f7a4584-8074-4340-ae63-b78621c75919")
    print(fetch_by_profile_id)

    config = statscc_handler.fetch_config()
    print(config)

if __name__ == "__main__":
    main()