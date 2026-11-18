import json
from unittest.mock import Mock, patch

import pytest

from ws_api import LoginFailedException, WealthsimpleAPI, WSAPISession
from ws_api.wealthsimple_api import WealthsimpleAPIBase

OPTIONS = {"challenge": "test-challenge", "rpId": "wealthsimple.com"}
ASSERTION = {
    "id": "credential-id",
    "rawId": "credential-id",
    "type": "public-key",
    "response": {
        "clientDataJSON": "data",
        "authenticatorData": "data",
        "signature": "sig",
    },
}


@pytest.fixture
def transport():
    def bootstrap(api):
        api.session.client_id = "client-id"
        api.session.wssdi = "device-id"

    with (
        patch.object(WealthsimpleAPI, "_bootstrap_device_id_and_client", bootstrap),
        patch("curl_cffi.requests.Session.request") as request,
    ):
        yield request


def responses(transport, *bodies):
    transport.side_effect = [
        Mock(status_code=200, **{"json.return_value": body}) for body in bodies
    ]


@pytest.mark.parametrize("with_callback", [False, True])
def test_passkey_returns_a_reusable_session(transport, with_callback):
    responses(
        transport,
        {"access_token": "app-token"},
        {"challenge_key": "challenge-key", "options": OPTIONS},
        {
            "access_token": "user-token",
            "refresh_token": "refresh-token",
            "token_type": "Bearer",
        },
        {"data": {"securitySearch": {"results": []}}},
    )
    authenticate = Mock(return_value=ASSERTION)

    saved = []
    if with_callback:
        session = WealthsimpleAPI.login_with_passkey(
            None, authenticate, persist_session_fct=saved.append
        )
        assert saved == [session.to_json()]
    else:
        session = WealthsimpleAPI.login_with_passkey(None, authenticate)
    ws = WealthsimpleAPI.from_token(WSAPISession.from_json(session.to_json()))

    authenticate.assert_called_once_with(OPTIONS)
    assert ws.session.access_token == "user-token"
    assert ws.session.refresh_token == "refresh-token"
    bootstrap, options, exchange, verify = [c.kwargs for c in transport.call_args_list]
    assert bootstrap["json"] == {
        "grant_type": "client_credentials",
        "scope": "read",
        "client_id": "client-id",
    }
    assert (
        options["url"]
        == "https://api.production.wealthsimple.com/v1/webauthn/authentication/options"
    )
    assert options["json"] is None
    assert options["headers"]["Authorization"] == "Bearer app-token"
    assert (
        exchange["url"] == "https://api.production.wealthsimple.com/v1/oauth/v2/token"
    )
    assert exchange["json"]["scope"] == WealthsimpleAPI.SCOPE_READ_ONLY
    assert exchange["json"]["grant_type"] == "webauthn"
    assert exchange["json"]["challenge_key"] == "challenge-key"
    assert exchange["json"]["webauthn_credential"] == ASSERTION
    assert exchange["json"]["skip_provision"] is True
    assert exchange["json"]["redirect_uri"] == "https://my.wealthsimple.com/app/login"
    assert "Authorization" not in exchange["headers"]
    assert (
        exchange["headers"]["x-ws-session-id"] == options["headers"]["x-ws-session-id"]
    )
    assert verify["headers"]["Authorization"] == "Bearer user-token"


@pytest.mark.parametrize("granted_scope", ["invest.write", "invest.write trade.write"])
def test_passkey_accepts_only_explicitly_requested_scopes(transport, granted_scope):
    responses(
        transport,
        {"access_token": "app-token"},
        {"challenge_key": "key", "options": OPTIONS},
        {
            "access_token": "user-token",
            "refresh_token": "refresh-token",
            "token_type": "Bearer",
            "scope": granted_scope,
        },
    )
    saved = []
    if granted_scope == "invest.write":
        session = WealthsimpleAPI.login_with_passkey(
            None, lambda _: ASSERTION, saved.append, "invest.write"
        )
        assert saved == [session.to_json()]
    else:
        with pytest.raises(LoginFailedException, match="unexpected scopes"):
            WealthsimpleAPI.login_with_passkey(
                None, lambda _: ASSERTION, saved.append, "invest.write"
            )
        assert not saved

    assert transport.call_args_list[0].kwargs["json"]["scope"] == "read"
    assert transport.call_args_list[2].kwargs["json"]["scope"] == "invest.write"


def test_passkey_persistence_uses_the_supplied_session_name(transport):
    responses(
        transport,
        {"access_token": "app-token"},
        {"challenge_key": "challenge-key", "options": OPTIONS},
        {
            "access_token": "user-token",
            "refresh_token": "refresh-token",
            "token_type": "Bearer",
        },
    )
    saved = []

    def persist(session_json, username):
        saved.append((session_json, username))

    session = WealthsimpleAPI.login_with_passkey(
        "personal",
        lambda _: ASSERTION,
        persist_session_fct=persist,
    )

    assert saved == [(session.to_json(), "personal")]
    assert transport.call_count == 3


@pytest.mark.parametrize(
    "assertion", [None, {}, {"type": "public-key", "response": {}}]
)
def test_missing_assertion_is_not_exchanged(transport, assertion):
    responses(
        transport,
        {"access_token": "app-token"},
        {"challenge_key": "key", "options": OPTIONS},
    )

    with pytest.raises(LoginFailedException, match="assertion"):
        WealthsimpleAPI.login_with_passkey(None, lambda _: assertion)

    assert transport.call_count == 2


@pytest.mark.parametrize(
    "body",
    [
        {"token_type": "DPoP", "access_token": "secret", "refresh_token": "secret"},
        {"token_type": "Bearer", "access_token": "secret"},
        {
            "token_type": "Bearer",
            "access_token": "secret",
            "refresh_token": "secret",
            "scope": "invest.read invest.write",
        },
        {
            "error": "login_challenge_required",
            "purpose": "login_approval",
            "extra": "secret",
        },
    ],
)
def test_rejected_exchange_does_not_expose_response_or_retry(transport, body):
    responses(
        transport,
        {"access_token": "app-token"},
        {"challenge_key": "key", "options": OPTIONS},
        body,
    )

    with pytest.raises(LoginFailedException) as error:
        WealthsimpleAPI.login_with_passkey(None, lambda _: ASSERTION)

    assert "secret" not in str(error.value)
    assert transport.call_count == 3


def test_chrome_handoff_embeds_only_options_and_reads_an_unprinted_assertion(capsys):
    with patch("getpass.getpass", return_value=json.dumps(ASSERTION)) as prompt:
        assert WealthsimpleAPIBase.passkey_chrome_assertion(OPTIONS) == ASSERTION

    prompt.assert_called_once()
    console = capsys.readouterr().out
    assert "https://my.wealthsimple.com" in console
    assert "PublicKeyCredential.parseRequestOptionsFromJSON" in console
    assert console.index("const copyAssertion = copy;") < console.index(
        "await navigator.credentials.get"
    )
    assert "copyAssertion(JSON.stringify(credential.toJSON()))" in console
    assert OPTIONS["challenge"] in console
    assert ASSERTION["id"] not in console
