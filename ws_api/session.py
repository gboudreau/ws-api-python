from dataclasses import dataclass, asdict
import json


@dataclass
class OAuthSession:
    """
    A class representing an OAuth session.

    Attributes:
        client_id: OAuth Client ID, used in OAuth requests.
        access_token: OAuth Access Token, used to authenticate API requests.
        refresh_token: OAuth Refresh Token, used to obtain new access tokens when they expire.
    """

    client_id: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None


@dataclass
class WSAPISession(OAuthSession):
    """
    A class representing a WSAPI session, extending OAuthSession.

    Attributes:
        session_id: Session ID, sent in headers for OAuth requests.
        wssdi: Device ID, sent in headers of API requests.
        token_info: Cached result of getTokenInfo().
    """

    session_id: str | None = None
    wssdi: str | None = None
    token_info: dict | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "WSAPISession":
        return cls(**json.loads(json_str))
