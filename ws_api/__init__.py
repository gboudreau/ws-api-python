from ws_api.exceptions import (
    CurlException,
    LoginFailedException,
    ManualLoginRequired,
    OTPRequiredException,
    UnexpectedException,
    WSApiException,
)
from ws_api.session import WSAPISession
from ws_api.wealthsimple_api import WealthsimpleAPI

__version__ = "0.36.1"

__all__ = [
    "CurlException",
    "LoginFailedException",
    "ManualLoginRequired",
    "OTPRequiredException",
    "UnexpectedException",
    "WSApiException",
    "WSAPISession",
    "WealthsimpleAPI",
    "__version__",
]
