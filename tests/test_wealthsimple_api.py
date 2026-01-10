import uuid
from unittest.mock import MagicMock, patch

import pytest

from ws_api.session import WSAPISession
from ws_api.wealthsimple_api import WealthsimpleAPI, WealthsimpleAPIBase


def test_wealthsimple_api_set_user_agent():
    WealthsimpleAPI.set_user_agent("Test User Agent")
    assert WealthsimpleAPI.user_agent == "Test User Agent"


def test_wealthsimple_api_uuidv4():
    uuid_str = WealthsimpleAPI.uuidv4()
    assert isinstance(uuid_str, str)
    assert len(uuid_str) == 36
    uuid.UUID(uuid_str, version=4)


@pytest.fixture
def mock_session():
    sess = WSAPISession()
    sess.client_id = "test_client_id"
    sess.access_token = "test_access_token"
    sess.refresh_token = "test_refresh_token"
    sess.session_id = "test_session_id"
    sess.wssdi = "test_wssdi"
    return sess


def test_wealthsimple_api_init_with_session(mock_session):
    api = WealthsimpleAPI(mock_session)
    assert api.session.client_id == "test_client_id"
    assert api.session.access_token == "test_access_token"
    assert api.session.refresh_token == "test_refresh_token"
    assert api.session.session_id == "test_session_id"
    assert api.session.wssdi == "test_wssdi"


@patch("requests.request")
def test_send_http_request_post(mock_request, mock_session):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"status": "ok"}
    mock_request.return_value = mock_resp

    api = WealthsimpleAPIBase(mock_session)

    result = api.send_http_request(
        "https://test.example.com/api",
        "POST",
        {"grant_type": "password", "username": "test", "password": "test"},
    )

    assert result == {"status": "ok"}

    mock_request.assert_called_once()
    args, kwargs = mock_request.call_args
    assert args[0] == "POST"
    assert args[1] == "https://test.example.com/api"
    assert kwargs["json"] == {
        "grant_type": "password",
        "username": "test",
        "password": "test",
    }
    headers = kwargs["headers"]
    assert headers["Content-Type"] == "application/json"
    assert headers["x-ws-session-id"] == "test_session_id"
    assert headers["Authorization"] == "Bearer test_access_token"
    assert headers["x-ws-device-id"] == "test_wssdi"


@patch("requests.request")
def test_send_get_request(mock_request, mock_session):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"status": "ok"}
    mock_request.return_value = mock_resp

    api = WealthsimpleAPIBase(mock_session)

    result = api.send_get("https://test.example.com/get")

    assert result == {"status": "ok"}

    mock_request.assert_called_once()
    args, kwargs = mock_request.call_args
    assert args[0] == "GET"
    assert args[1] == "https://test.example.com/get"
    headers = kwargs["headers"]
    assert "x-ws-session-id" in headers
    assert headers["x-ws-session-id"] == "test_session_id"
