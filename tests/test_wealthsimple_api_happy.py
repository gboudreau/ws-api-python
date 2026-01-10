from unittest.mock import MagicMock, patch

import pytest

from ws_api.exceptions import WSApiException
from ws_api.session import WSAPISession
from ws_api.wealthsimple_api import WealthsimpleAPI, WealthsimpleAPIBase


@pytest.fixture
def api_base():
    return WealthsimpleAPIBase()


@pytest.fixture
def api_with_session():
    sess = WSAPISession()
    sess.client_id = "test_client"
    sess.session_id = "test_session"
    sess.wssdi = "test_wssdi"
    return WealthsimpleAPIBase(sess)


@pytest.fixture
def api():
    return WealthsimpleAPI()


def test_send_http_request_return_headers(api_base):
    """Test send_http_request with return_headers=True path."""
    with patch("ws_api.wealthsimple_api.requests.request") as mock_request:
        mock_resp = MagicMock()
        mock_resp.headers = {"Set-Cookie": "wssdi=test; path=/"}
        mock_resp.text = "response body"
        mock_request.return_value = mock_resp

        result = api_base.send_http_request(
            "https://test.com", "GET", return_headers=True
        )

        expected_headers = "Set-Cookie: wssdi=test; path=/\r\n\r\nresponse body"
        assert result == expected_headers


def test_send_post(api_base):
    """Test send_post delegation."""
    with patch("ws_api.wealthsimple_api.requests.request") as mock_request:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True}
        mock_request.return_value = mock_resp

        result = api_base.send_post("https://test.com", {"data": 1})

        assert result == {"ok": True}


def test_start_session_preserves_existing_session(api_with_session):
    """Test start_session preserves existing session values."""
    # start_session should not overwrite existing session values
    api_with_session.start_session()
    assert api_with_session.session.client_id == "test_client"
    assert api_with_session.session.wssdi == "test_wssdi"


def test_check_oauth_token_refresh(api_base):
    """Test check_oauth_token refresh path."""
    api_base.session.refresh_token = "old_refresh"
    api_base.session.client_id = "test_client"

    with patch.object(api_base, "send_post") as mock_post:
        mock_post.return_value = {
            "access_token": "new_access",
            "refresh_token": "new_refresh",
        }
        with patch.object(
            api_base,
            "search_security",
            side_effect=WSApiException(
                "Not Authorized.", {"message": "Not Authorized."}
            ),
        ):
            api_base.check_oauth_token()

        mock_post.assert_called_once()
        assert api_base.session.access_token == "new_access"
        assert api_base.session.refresh_token == "new_refresh"


def test_login_internal_happy(api_base):
    """Test login_internal happy path."""
    api_base.session.client_id = "test_client"

    with patch.object(api_base, "send_post") as mock_post:
        mock_post.return_value = {
            "access_token": "access_token",
            "refresh_token": "refresh_token",
        }
        sess = api_base.login_internal("user", "pass")
        assert sess.access_token == "access_token"
        assert sess.refresh_token == "refresh_token"


def test_do_graphql_query_simple(api_base):
    """Test do_graphql_query basic path."""
    fake_data = {
        "data": {
            "identity": {
                "accounts": {
                    "edges": [{"node": {"id": "acc1"}}],
                    "pageInfo": {"hasNextPage": False},
                }
            }
        }
    }

    with patch.object(api_base, "send_post") as mock_post:
        mock_post.return_value = fake_data
        result = api_base.do_graphql_query(
            "FetchAllAccountFinancials",
            {"identityId": "id"},
            "identity.accounts.edges",
            "array",
        )
        assert result == [{"id": "acc1"}]


def test_get_token_info(api_base):
    """Test get_token_info with caching."""
    fake_info = {"identity_canonical_id": "fake_id"}

    with patch.object(api_base, "send_get") as mock_get:
        mock_get.return_value = fake_info
        result1 = api_base.get_token_info()
        assert result1 == fake_info
        result2 = api_base.get_token_info()
        assert result2 == fake_info
        mock_get.assert_called_once()


@pytest.mark.parametrize(
    "unified_type, expected_desc",
    [
        ("SELF_DIRECTED_RRSP", "RRSP: self-directed"),
        ("MANAGED_TFSA", "TFSA: managed"),
        ("SELF_DIRECTED_NON_REGISTERED_MARGIN", "Non-registered: self-directed margin"),
    ],
)
def test_account_add_description(api, unified_type, expected_desc):
    """Test _account_add_description various cases."""
    account = {
        "id": "acc1",
        "unifiedAccountType": unified_type,
        "status": "open",
        "accountOwnerConfiguration": "SINGLE_OWNER",
        "accountFeatures": [],
        "custodianAccounts": [],
    }
    api._account_add_description(account)
    assert account["description"] == expected_desc


def test_account_add_description_cash(api):
    """Test _account_add_description for CASH type."""
    account = {
        "id": "acc1",
        "unifiedAccountType": "CASH",
        "status": "open",
        "accountOwnerConfiguration": "SINGLE_OWNER",
        "accountFeatures": [],
        "custodianAccounts": [{"branch": "WS", "id": "cust123", "status": "open"}],
    }
    api._account_add_description(account)
    assert account["description"] == "Cash"
    assert account["number"] == "cust123"


def test_get_account_balances(api):
    """Test get_account_balances happy path."""
    fake_accounts = [
        {
            "custodianAccounts": [
                {
                    "financials": {
                        "balance": [
                            {"securityId": "sec-c-cad", "quantity": 100.0},
                        ]
                    }
                }
            ]
        }
    ]

    with patch.object(api, "do_graphql_query", return_value=fake_accounts):
        balances = api.get_account_balances("acc_id")
        assert balances["sec-c-cad"] == 100.0


def test_security_id_to_symbol_no_cache(api):
    """Test security_id_to_symbol without cache, exception path."""
    with patch.object(api, "get_security_market_data", side_effect=WSApiException("")):
        symbol = api.security_id_to_symbol("sec123")
        assert symbol == "[sec123]"


def test_get_etf_details(api):
    """Smoke test get_etf_details."""
    fake = {"id": "fund1"}
    with patch.object(api, "do_graphql_query", return_value=fake):
        result = api.get_etf_details("fund_id")
        assert result == fake


def test_get_transfer_details(api):
    """Smoke test get_transfer_details."""
    fake = {"id": "trans1"}
    with patch.object(api, "do_graphql_query", return_value=fake):
        result = api.get_transfer_details("trans_id")
        assert result == fake


def test_get_security_market_data(api):
    """Smoke test get_security_market_data without cache."""
    fake = {"stock": {"symbol": "TEST"}}
    with patch.object(api, "do_graphql_query", return_value=fake):
        result = api.get_security_market_data("sec1")
        assert result == fake


def test_get_security_historical_quotes(api):
    """Smoke test get_security_historical_quotes."""
    fake = [{"date": "2023-01-01"}]
    with patch.object(api, "do_graphql_query", return_value=fake):
        result = api.get_security_historical_quotes("sec1")
        assert result == fake


def test_get_corporate_action_child_activities(api):
    """Smoke test get_corporate_action_child_activities."""
    fake = [{"canonicalId": "child1"}]
    with patch.object(api, "do_graphql_query", return_value=fake):
        result = api.get_corporate_action_child_activities("act_id")
        assert result == fake


def test_get_statement_transactions(api):
    """Smoke test get_statement_transactions."""
    fake_transactions = [{"balance": 100}]
    fake_statements = [{"data": {"currentTransactions": fake_transactions}}]
    with patch.object(api, "do_graphql_query", return_value=fake_statements):
        result = api.get_statement_transactions("acc_id", "2023-01-01")
        assert result == fake_transactions


def test_get_identity_positions(api):
    """Smoke test get_identity_positions."""
    api.session.token_info = {"identity_canonical_id": "fake_id"}
    fake_positions = [{"id": "pos1"}]
    with patch.object(api, "do_graphql_query", return_value=fake_positions):
        result = api.get_identity_positions(["sec1"], "CAD")
        assert result == fake_positions


def test_get_creditcard_account(api):
    """Smoke test get_creditcard_account."""
    fake = {"id": "cc1"}
    with patch.object(api, "do_graphql_query", return_value=fake):
        result = api.get_creditcard_account("cc_id")
        assert result == fake
