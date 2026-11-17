import runpy
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from ws_api import OTPRequiredException, WSAPISession


def test_example_login_uses_hidden_prompts_for_secrets():
    keyring = MagicMock()
    keyring.get_password.side_effect = [None, WSAPISession().to_json()]

    def read_username(prompt):
        assert prompt == "Wealthsimple username (email): "
        return "user@example.com"

    with (
        patch.dict("sys.modules", {"keyring": keyring}),
        patch("ws_api.WealthsimpleAPI") as api,
        patch("builtins.input", side_effect=read_username) as username_prompt,
        patch("getpass.getpass", side_effect=["secret-password", "123456"]) as secret_prompt,
    ):
        api.login.side_effect = [OTPRequiredException(), None]
        ws = api.from_token.return_value
        ws.get_net_worth_with_history.return_value = {"balance": {"amount": "0"}}
        ws.get_net_worth_accounts.return_value = {"accounts": []}
        ws.get_accounts.return_value = []
        ws.get_identity_historical_financials.return_value = []

        example = runpy.run_path(str(Path(__file__).with_name("test_full_example.py")))
        example["WSApiTest"]().main()

    username_prompt.assert_called_once_with("Wealthsimple username (email): ")
    assert secret_prompt.call_args_list == [call("Password: "), call("TOTP code: ")]
    assert [login.args for login in api.login.call_args_list] == [
        ("user@example.com", "secret-password", None),
        ("user@example.com", "secret-password", "123456"),
    ]
