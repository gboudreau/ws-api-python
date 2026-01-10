import json

from ws_api.session import OAuthSession, WSAPISession


def test_oauth_session_init():
    session = OAuthSession()
    assert session.client_id is None
    assert session.access_token is None
    assert session.refresh_token is None


def test_wsapi_session_init():
    session = WSAPISession()
    assert session.client_id is None
    assert session.access_token is None
    assert session.refresh_token is None
    assert session.session_id is None
    assert session.wssdi is None
    assert session.token_info is None


def test_wsapi_session_to_json():
    session = WSAPISession()
    session.client_id = "test_client_id"
    session.access_token = "test_access_token"
    session.refresh_token = "test_refresh_token"
    session.session_id = "test_session_id"
    session.wssdi = "test_wssdi"
    session.token_info = {"key": "value"}

    json_str = session.to_json()
    data = json.loads(json_str)

    assert data["client_id"] == "test_client_id"
    assert data["access_token"] == "test_access_token"
    assert data["refresh_token"] == "test_refresh_token"
    assert data["session_id"] == "test_session_id"
    assert data["wssdi"] == "test_wssdi"
    assert data["token_info"] == {"key": "value"}


def test_wsapi_session_from_json():
    data = {
        "client_id": "test_client_id",
        "access_token": "test_access_token",
        "refresh_token": "test_refresh_token",
        "session_id": "test_session_id",
        "wssdi": "test_wssdi",
        "token_info": {"key": "value"},
    }
    json_str = json.dumps(data)

    session = WSAPISession.from_json(json_str)

    assert session.client_id == "test_client_id"
    assert session.access_token == "test_access_token"
    assert session.refresh_token == "test_refresh_token"
    assert session.session_id == "test_session_id"
    assert session.wssdi == "test_wssdi"
    assert session.token_info == {"key": "value"}
