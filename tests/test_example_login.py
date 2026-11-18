import runpy
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from ws_api import OTPRequiredException, WSAPISession

LOGIN_CHOICE = "Use a passkey to log in? [Y/n]: "
USERNAME_PROMPT = "Session name (use your Wealthsimple email for password sign-in): "


def run_example(api):
    ws = api.from_token.return_value
    ws.get_net_worth_with_history.return_value = {"balance": {"amount": "0"}}
    ws.get_net_worth_accounts.return_value = {"accounts": []}
    ws.get_accounts.return_value = []
    ws.get_identity_historical_financials.return_value = []
    example = runpy.run_path(str(Path(__file__).with_name("test_full_example.py")))
    example["WSApiTest"]().main()


def test_example_login_uses_hidden_prompts_for_secrets():
    keyring = MagicMock()
    keyring.get_password.return_value = None

    with (
        patch.dict("sys.modules", {"keyring": keyring}),
        patch("ws_api.WealthsimpleAPI") as api,
        patch("builtins.input", side_effect=["user@example.com", "n"]) as prompt,
        patch(
            "getpass.getpass", side_effect=["secret-password", "123456"]
        ) as secret_prompt,
    ):
        api.login.side_effect = [OTPRequiredException(), WSAPISession()]
        run_example(api)

    assert prompt.call_args_list == [
        call(USERNAME_PROMPT),
        call(LOGIN_CHOICE),
    ]
    api.login_with_passkey.assert_not_called()
    assert secret_prompt.call_args_list == [call("Password: "), call("TOTP code: ")]
    assert [login.args for login in api.login.call_args_list] == [
        ("user@example.com", "secret-password", None),
        ("user@example.com", "secret-password", "123456"),
    ]
    assert api.from_token.call_args.args[1:] == (
        api.login.call_args.kwargs["persist_session_fct"],
        "user@example.com",
    )


@pytest.mark.parametrize("email", ["passkey@example.com", None])
def test_example_passkey_keeps_the_chosen_session_name(email):
    session = WSAPISession(
        access_token="access", refresh_token="refresh", token_info={"email": email}
    )
    keyring = MagicMock()
    keyring.get_password.return_value = None
    session_name = "personal"
    with (
        patch.dict("sys.modules", {"keyring": keyring}),
        patch("ws_api.WealthsimpleAPI") as api,
        patch("builtins.input", side_effect=[session_name, ""]) as prompt,
        patch("getpass.getpass") as password_prompt,
    ):
        api.login_with_passkey.return_value = session
        api.from_token.return_value.session = session
        run_example(api)

        assert prompt.call_args_list == [call(USERNAME_PROMPT), call(LOGIN_CHOICE)]
        password_prompt.assert_not_called()
        api.login.assert_not_called()
        passed_session, persist, username = api.from_token.call_args.args
        api.login_with_passkey.assert_called_once_with(
            session_name,
            api.passkey_chrome_assertion,
            persist_session_fct=persist,
        )
        assert passed_session == session
        assert username == session_name
        persist("refreshed-session", username)
        keyring.set_password.assert_called_once_with(
            f"wealthsimple.api.{session_name}", "session", "refreshed-session"
        )
