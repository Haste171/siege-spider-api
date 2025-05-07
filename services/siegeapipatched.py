# services/siege_api_safe.py
import time
import logging
from siegeapi import Auth, InvalidRequest

logger = logging.getLogger(__name__)

class ExpiredAuthException(Exception):
    pass

class SiegeAPIPatched(Auth):
    MAX_TOTAL_RETRIES = 1

    async def get(self, *args, retries: int = 0, json_: bool = True, new: bool = False, **kwargs):
        if retries >= self.MAX_TOTAL_RETRIES:
            raise Exception("Maximum retry limit reached in SafeSiegeAuth.get()")

        try:
            return await super().get(*args, retries=retries, json_=json_, new=new, **kwargs)
        except InvalidRequest as e:
            if "HTTP 401" in str(e) and retries < self.MAX_TOTAL_RETRIES:
                raise ExpiredAuthException("Refresh of auth is required!")
            raise e

    def get_app_id(self):
        return self.appid

    def get_token(self):
        return self.token

    def get_session_id(self):
        return self.sessionid

    def get_key(self):
        return self.key