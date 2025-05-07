import json
import requests

class TwitchHandler:
    def __init__(self):
        self.base_url = "https://gql.twitch.tv/gql"

    def check_stream_data(self, username: str):
        payload = json.dumps([
                {
                    "operationName": "CommunityTab",
                    "variables": {
                        "login": username
                    },
                    "extensions": {
                        "persistedQuery": {
                            "version": 1,
                            "sha256Hash": "2e71a3399875770c1e5d81a9774d9803129c44cf8f6bad64973aa0d239a88caf"
                        }
                    }
                }
            ])

        headers = {
            'Client-Id': 'kimne78kx3ncx6brgo4mv6wki5h1ko',
            'X-Device-Id': 'Jkz41qWBcHP8apxspDJUL8oi05k6I1ei',
            'Content-Type': 'application/json'
        }

        response = requests.post(self.base_url, headers=headers, data=payload)
        if response.status_code == 200:
            return response.json()
        else:
            raise RuntimeError(f"Failed to run request (URL: {self.base_url})), response code: {response.status_code}\n\n{response.text}")

if __name__ == "__main__":
    handler = TwitchHandler()
    data = handler.check_stream_data("beaulo")
    print(data)