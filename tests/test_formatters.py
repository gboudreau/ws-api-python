"""Unit tests for formatter helper functions in ws_api/formatters.py."""

from unittest.mock import MagicMock

import pytest

from ws_api.formatters import (
    _format_corporate_action_subdivision,
    _format_credit_card_description,
    _format_eft,
    _format_institutional_transfer,
    _format_internal_transfer,
    _format_trade,
)


# --- _format_credit_card_description ---


class TestFormatCreditCardDescription:
    @pytest.mark.parametrize(
        "status, expected_prefix",
        [
            ("authorized", "(Pending) Credit card purchase: "),
            ("settled", "Credit card purchase: "),
        ],
    )
    def test_purchase(self, status, expected_prefix):
        act = {
            "type": "CREDIT_CARD",
            "subType": "PURCHASE",
            "status": status,
            "spendMerchant": "Amazon",
        }
        assert _format_credit_card_description(act) is True
        assert act["description"] == f"{expected_prefix}Amazon"

    @pytest.mark.parametrize(
        "status, expected_prefix",
        [
            ("authorized", "(Pending) Credit card refund: "),
            ("settled", "Credit card refund: "),
        ],
    )
    def test_hold(self, status, expected_prefix):
        act = {
            "type": "CREDIT_CARD",
            "subType": "HOLD",
            "status": status,
            "spendMerchant": "Costco",
        }
        assert _format_credit_card_description(act) is True
        assert act["description"] == f"{expected_prefix}Costco"

    def test_refund(self):
        act = {
            "type": "CREDIT_CARD",
            "subType": "REFUND",
            "spendMerchant": "BestBuy",
        }
        assert _format_credit_card_description(act) is True
        assert act["description"] == "Credit card refund: BestBuy"

    def test_payment(self):
        act = {"type": "CREDIT_CARD", "subType": "PAYMENT"}
        assert _format_credit_card_description(act) is True
        assert act["description"] == "Credit card payment"

    def test_credit_card_payment_type(self):
        act = {"type": "CREDIT_CARD_PAYMENT", "subType": "SOMETHING"}
        assert _format_credit_card_description(act) is True
        assert act["description"] == "Credit card payment"

    def test_non_matching_type(self):
        act = {"type": "DEPOSIT", "subType": "EFT"}
        assert _format_credit_card_description(act) is False
        assert "description" not in act


# --- _format_trade ---


class TestFormatTrade:
    def _mock_api(self, symbol="AAPL"):
        api = MagicMock()
        api.security_id_to_symbol.return_value = symbol
        return api

    def test_diy_buy(self):
        api = self._mock_api("AAPL")
        act = {
            "type": "DIY_BUY",
            "subType": "MARKET_ORDER",
            "securityId": "sec-1",
            "assetQuantity": "10",
            "amount": "1500",
        }
        assert _format_trade(act, api) is True
        assert act["description"] == "Market order: buy 10.0 x AAPL @ 150.0"

    def test_diy_sell(self):
        api = self._mock_api("MSFT")
        act = {
            "type": "DIY_SELL",
            "subType": "MARKET_ORDER",
            "securityId": "sec-2",
            "assetQuantity": "5",
            "amount": "2000",
        }
        assert _format_trade(act, api) is True
        assert act["description"] == "Market order: sell 5.0 x MSFT @ 400.0"

    def test_managed_buy(self):
        api = self._mock_api("XGRO")
        act = {
            "type": "MANAGED_BUY",
            "subType": "MARKET_ORDER",
            "securityId": "sec-3",
            "assetQuantity": "20",
            "amount": "500",
        }
        assert _format_trade(act, api) is True
        assert act["description"] == "Managed transaction: buy 20.0 x XGRO @ 25.0"

    def test_crypto_buy(self):
        api = self._mock_api("BTC")
        act = {
            "type": "CRYPTO_BUY",
            "subType": "MARKET_ORDER",
            "securityId": "sec-4",
            "assetQuantity": "0.5",
            "amount": "25000",
        }
        assert _format_trade(act, api) is True
        assert act["description"] == "Crypto Market order: buy 0.5 x BTC @ 50000.0"

    def test_asset_quantity_none(self):
        api = self._mock_api("AAPL")
        act = {
            "type": "DIY_BUY",
            "subType": "MARKET_ORDER",
            "securityId": "sec-1",
            "assetQuantity": None,
            "amount": "1500",
        }
        assert _format_trade(act, api) is True
        assert act["description"] == "Market order: buy TBD"

    def test_non_matching_type(self):
        api = self._mock_api()
        act = {"type": "DEPOSIT", "subType": "EFT"}
        assert _format_trade(act, api) is False


# --- _format_eft ---


class TestFormatEft:
    def _mock_api(
        self, nickname="My Bank", account_number="****1234", account_name="Chequing"
    ):
        api = MagicMock()
        bank_account = {
            "nickname": nickname,
            "accountNumber": account_number,
            "accountName": account_name,
        }
        api.get_etf_details.return_value = {
            "source": {"bankAccount": bank_account},
            "destination": {"bankAccount": bank_account},
        }
        return api

    def test_deposit_eft(self):
        api = self._mock_api()
        act = {"type": "DEPOSIT", "subType": "EFT", "externalCanonicalId": "ext-1"}
        assert _format_eft(act, api) is True
        assert act["description"] == "Deposit: EFT from My Bank ****1234"

    def test_withdrawal_eft(self):
        api = self._mock_api()
        act = {"type": "WITHDRAWAL", "subType": "EFT", "externalCanonicalId": "ext-2"}
        assert _format_eft(act, api) is True
        assert act["description"] == "Withdrawal: EFT to My Bank ****1234"

    def test_falls_back_to_account_name(self):
        api = self._mock_api(nickname=None, account_name="Savings")
        act = {"type": "DEPOSIT", "subType": "EFT", "externalCanonicalId": "ext-3"}
        assert _format_eft(act, api) is True
        assert act["description"] == "Deposit: EFT from Savings ****1234"

    def test_non_eft_subtype(self):
        api = self._mock_api()
        act = {
            "type": "DEPOSIT",
            "subType": "E_TRANSFER",
            "externalCanonicalId": "ext-4",
        }
        assert _format_eft(act, api) is False


# --- _format_internal_transfer ---


class TestFormatInternalTransfer:
    def _mock_api(self, accounts=None):
        api = MagicMock()
        api.get_accounts.return_value = accounts or []
        return api

    def test_source_with_matching_account(self):
        accounts = [
            {"id": "acc-2", "description": "TFSA: self-directed", "number": "ABC123"}
        ]
        api = self._mock_api(accounts)
        act = {
            "type": "INTERNAL_TRANSFER",
            "subType": "SOURCE",
            "opposingAccountId": "acc-2",
        }
        assert _format_internal_transfer(act, api) is True
        assert (
            act["description"]
            == "Money transfer: to Wealthsimple TFSA: self-directed (ABC123)"
        )

    def test_destination_with_matching_account(self):
        accounts = [{"id": "acc-1", "description": "Cash", "number": "DEF456"}]
        api = self._mock_api(accounts)
        act = {
            "type": "INTERNAL_TRANSFER",
            "subType": "DESTINATION",
            "opposingAccountId": "acc-1",
        }
        assert _format_internal_transfer(act, api) is True
        assert act["description"] == "Money transfer: from Wealthsimple Cash (DEF456)"

    def test_asset_movement_type(self):
        accounts = [{"id": "acc-3", "description": "RRSP: managed", "number": "GHI789"}]
        api = self._mock_api(accounts)
        act = {
            "type": "ASSET_MOVEMENT",
            "subType": "SOURCE",
            "opposingAccountId": "acc-3",
        }
        assert _format_internal_transfer(act, api) is True
        assert (
            act["description"]
            == "Money transfer: to Wealthsimple RRSP: managed (GHI789)"
        )

    def test_no_matching_account_falls_back(self):
        api = self._mock_api([])
        act = {
            "type": "INTERNAL_TRANSFER",
            "subType": "SOURCE",
            "opposingAccountId": "acc-unknown",
        }
        assert _format_internal_transfer(act, api) is True
        assert act["description"] == "Money transfer: to Wealthsimple acc-unknown"

    def test_non_matching_type(self):
        api = self._mock_api()
        act = {"type": "DEPOSIT", "subType": "EFT"}
        assert _format_internal_transfer(act, api) is False


# --- _format_institutional_transfer ---


class TestFormatInstitutionalTransfer:
    def _mock_api(self, details=None):
        api = MagicMock()
        api.get_transfer_details.return_value = details
        return api

    def test_transfer_in_with_details(self):
        details = {
            "transferType": "full_transfer",
            "clientAccountType": "rrsp",
            "institutionName": "TD Bank",
            "redactedInstitutionAccountNumber": "1234",
        }
        api = self._mock_api(details)
        act = {
            "type": "INSTITUTIONAL_TRANSFER_INTENT",
            "subType": "TRANSFER_IN",
            "externalCanonicalId": "xfer-1",
        }
        assert _format_institutional_transfer(act, api) is True
        assert (
            act["description"]
            == "Institutional transfer: Full-transfer RRSP account transfer from TD Bank ****1234"
        )

    def test_transfer_in_without_details(self):
        api = self._mock_api(details=[])  # non-dict
        act = {
            "type": "INSTITUTIONAL_TRANSFER_INTENT",
            "subType": "TRANSFER_IN",
            "externalCanonicalId": "xfer-2",
        }
        assert _format_institutional_transfer(act, api) is True
        assert (
            act["description"]
            == "Institutional transfer:   account transfer from  ****"
        )

    def test_transfer_out(self):
        api = self._mock_api()
        act = {
            "type": "INSTITUTIONAL_TRANSFER_INTENT",
            "subType": "TRANSFER_OUT",
            "institutionName": "RBC",
        }
        assert _format_institutional_transfer(act, api) is True
        assert act["description"] == "Institutional transfer: transfer to RBC"

    def test_non_matching_type(self):
        api = self._mock_api()
        act = {"type": "DEPOSIT", "subType": "EFT"}
        assert _format_institutional_transfer(act, api) is False

    def test_non_matching_subtype(self):
        api = self._mock_api()
        act = {"type": "INSTITUTIONAL_TRANSFER_INTENT", "subType": "UNKNOWN"}
        assert _format_institutional_transfer(act, api) is False


# --- _format_corporate_action_subdivision ---


class TestFormatCorporateActionSubdivision:
    def _mock_api(self, children=None, security=None):
        api = MagicMock()
        api.get_corporate_action_child_activities.return_value = children or []
        api.get_security_market_data.return_value = security
        return api

    def test_with_hold_and_receive(self):
        children = [
            {"entitlementType": "HOLD", "quantity": "100"},
            {"entitlementType": "RECEIVE", "quantity": "100"},
        ]
        api = self._mock_api(children)
        act = {
            "type": "CORPORATE_ACTION",
            "subType": "SUBDIVISION",
            "canonicalId": "ca-1",
            "assetSymbol": "SHOP",
            "currency": "CAD",
            "securityId": "sec-1",
        }
        assert _format_corporate_action_subdivision(act, api) is True
        assert act["description"] == "Subdivision: 100.0 -> 200.0 shares of SHOP"

    def test_without_matching_children(self):
        api = self._mock_api([])
        act = {
            "type": "CORPORATE_ACTION",
            "subType": "SUBDIVISION",
            "canonicalId": "ca-2",
            "assetSymbol": "GOOG",
            "amount": "50",
            "currency": "USD",
            "securityId": "sec-2",
        }
        assert _format_corporate_action_subdivision(act, api) is True
        assert act["description"] == "Subdivision: Received 50.0 new shares of GOOG"

    def test_currency_none_triggers_security_lookup(self):
        security = {"fundamentals": {"currency": "USD"}}
        api = self._mock_api(children=[], security=security)
        act = {
            "type": "CORPORATE_ACTION",
            "subType": "SUBDIVISION",
            "canonicalId": "ca-3",
            "assetSymbol": "TSLA",
            "amount": "10",
            "currency": None,
            "securityId": "sec-3",
        }
        assert _format_corporate_action_subdivision(act, api) is True
        api.get_security_market_data.assert_called_once_with("sec-3")
        assert act["currency"] == "USD"

    def test_currency_set_skips_security_lookup(self):
        api = self._mock_api(children=[])
        act = {
            "type": "CORPORATE_ACTION",
            "subType": "SUBDIVISION",
            "canonicalId": "ca-4",
            "assetSymbol": "AAPL",
            "amount": "5",
            "currency": "CAD",
            "securityId": "sec-4",
        }
        _format_corporate_action_subdivision(act, api)
        api.get_security_market_data.assert_not_called()

    def test_non_matching_type(self):
        api = self._mock_api()
        act = {"type": "DEPOSIT", "subType": "EFT"}
        assert _format_corporate_action_subdivision(act, api) is False

    def test_non_matching_subtype(self):
        api = self._mock_api()
        act = {"type": "CORPORATE_ACTION", "subType": "MERGER"}
        assert _format_corporate_action_subdivision(act, api) is False
