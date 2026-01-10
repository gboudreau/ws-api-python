import json
from abc import ABC


class OAuthSession(ABC):
    """
    A class representing an OAuth session.

    Attributes:
        client_id (str or None): OAuth Client ID, used in OAuth requests.
        access_token (str or None): OAuth Access Token, used to authenticate API requests.
        refresh_token (str or None): OAuth Refresh Token, used to obtain new access tokens when they expire.
    """

    def __init__(self):
        self.client_id: str | None = None
        self.access_token = None
        self.refresh_token = None


class WSAPISession(OAuthSession):
    """
    A class representing a WSAPI session, extending OAuthSession.

    Attributes:
        session_id (str or None): Session ID, sent in headers for OAuth requests.
        wssdi (str or None): Device ID, sent in headers of API requests.
        token_info (object or None): Cached result of getTokenInfo().
    """

    def __init__(self):
        super().__init__()
        self.session_id: str | None = None
        self.wssdi: str | None = None
        self.token_info = None

    def to_json(self):
        return json.dumps(self, default=lambda o: o.__dict__, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str):
        data = json.loads(json_str)
        obj = cls()
        obj.__dict__.update(data)
        return obj
