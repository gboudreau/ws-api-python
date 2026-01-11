import re
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from inspect import signature
from typing import Any

import requests

from ws_api.exceptions import (
    CurlException,
    LoginFailedException,
    ManualLoginRequired,
    OTPRequiredException,
    UnexpectedException,
    WSApiException,
)
from ws_api.formatters import (
    format_account_description,
    format_activity_description,
)
from ws_api.graphql_queries import GRAPHQL_QUERIES
from ws_api.session import WSAPISession


class WealthsimpleAPIBase:
    OAUTH_BASE_URL = "https://api.production.wealthsimple.com/v1/oauth/v2"
    GRAPHQL_URL = "https://my.wealthsimple.com/graphql"
    GRAPHQL_VERSION = "12"

    def __init__(self, sess: WSAPISession | None = None):
        self.security_market_data_cache_getter = None
        self.security_market_data_cache_setter = None
        self.session = WSAPISession()
        self.start_session(sess)

    user_agent: str | None = None

    @staticmethod
    def set_user_agent(user_agent: str) -> None:
        WealthsimpleAPI.user_agent = user_agent

    @staticmethod
    def uuidv4() -> str:
        return str(uuid.uuid4())

    def send_http_request(
        self,
        url: str,
        method: str = "POST",
        data: dict | None = None,
        headers: dict | None = None,
        return_headers: bool = False,
    ) -> Any:
        headers = headers or {}
        if method == "POST":
            headers["Content-Type"] = "application/json"

        if self.session.session_id:
            headers["x-ws-session-id"] = self.session.session_id

        if self.session.access_token and (
            not data or data.get("grant_type") != "refresh_token"
        ):
            headers["Authorization"] = f"Bearer {self.session.access_token}"

        if self.session.wssdi:
            headers["x-ws-device-id"] = self.session.wssdi

        if WealthsimpleAPI.user_agent:
            headers["User-Agent"] = WealthsimpleAPI.user_agent

        try:
            response = requests.request(method, url, json=data, headers=headers)

            if return_headers:
                # Combine headers and body as a single string
                response_headers = "\r\n".join(
                    f"{k}: {v}" for k, v in response.headers.items()
                )
                return f"{response_headers}\r\n\r\n{response.text}"

            return response.json()
        except requests.exceptions.RequestException as e:
            raise CurlException(f"HTTP request failed: {e}")

    def send_get(
        self, url: str, headers: dict | None = None, return_headers: bool = False
    ) -> Any:
        return self.send_http_request(
            url, "GET", headers=headers, return_headers=return_headers
        )

    def send_post(
        self,
        url: str,
        data: dict,
        headers: dict | None = None,
        return_headers: bool = False,
    ) -> Any:
        return self.send_http_request(
            url, "POST", data=data, headers=headers, return_headers=return_headers
        )

    def start_session(self, sess: WSAPISession | None = None):
        if sess:
            self.session.access_token = sess.access_token
            self.session.wssdi = sess.wssdi
            self.session.session_id = sess.session_id
            self.session.client_id = sess.client_id
            self.session.refresh_token = sess.refresh_token
            return

        app_js_url = None

        if not self.session.wssdi or not self.session.client_id:
            # Fetch login page
            response = self.send_get(
                "https://my.wealthsimple.com/app/login", return_headers=True
            )

            for line in response.splitlines():
                # Look for wssdi in set-cookie headers
                if not self.session.wssdi and "set-cookie:" in line.lower():
                    match = re.search(r"wssdi=([a-f0-9]+);", line, re.IGNORECASE)
                    if match:
                        self.session.wssdi = match.group(1)

                if not app_js_url and "<script" in line.lower():
                    match = re.search(
                        r'<script.*src="(.+/app-[a-f0-9]+\.js)', line, re.IGNORECASE
                    )
                    if match:
                        app_js_url = match.group(1)

            if not self.session.wssdi:
                raise UnexpectedException(
                    "Couldn't find wssdi in login page response headers."
                )

        if not self.session.client_id:
            if not app_js_url:
                raise UnexpectedException(
                    "Couldn't find app JS URL in login page response body."
                )

            # Fetch the app JS file
            response = self.send_get(app_js_url, return_headers=True)

            # Look for clientId in the app JS file
            match = re.search(
                r'production:.*clientId:"([a-f0-9]+)"', response, re.IGNORECASE
            )
            if match:
                self.session.client_id = match.group(1)

            if not self.session.client_id:
                raise UnexpectedException("Couldn't find clientId in app JS.")

        if not self.session.session_id:
            self.session.session_id = str(uuid.uuid4())

    def search_security(self, query):
        # Fetch security search results using GraphQL query
        return self.do_graphql_query(
            "FetchSecuritySearchResult",
            {"query": query},
            "securitySearch.results",
            "array",
        )

    def check_oauth_token(
        self, persist_session_fct: Callable | None = None, username=None
    ):
        if self.session.access_token:
            try:
                self.search_security("XEQT")
            except WSApiException as e:
                if e.response is None or e.response.get("message") != "Not Authorized.":
                    raise
                # Access token expired; try to refresh it below
            else:
                return

        if self.session.refresh_token:
            data = {
                "grant_type": "refresh_token",
                "refresh_token": self.session.refresh_token,
                "client_id": self.session.client_id,
            }
            headers = {
                "x-wealthsimple-client": "@wealthsimple/wealthsimple",
                "x-ws-profile": "invest",
            }
            response = self.send_post(f"{self.OAUTH_BASE_URL}/token", data, headers)
            if "access_token" not in response or "refresh_token" not in response:
                raise ManualLoginRequired(
                    f"OAuth token invalid and cannot be refreshed: {response.get('error', 'Invalid response from API')}"
                )
            self.session.access_token = response["access_token"]
            self.session.refresh_token = response["refresh_token"]
            if persist_session_fct:
                if len(signature(persist_session_fct).parameters) == 2:
                    persist_session_fct(self.session.to_json(), username)
                else:
                    persist_session_fct(self.session.to_json())
            return

        raise ManualLoginRequired("OAuth token invalid and cannot be refreshed.")

    SCOPE_READ_ONLY = "invest.read trade.read tax.read"
    SCOPE_READ_WRITE = (
        "invest.read trade.read tax.read invest.write trade.write tax.write"
    )

    def login_internal(
        self,
        username: str,
        password: str,
        otp_answer: str | None = None,
        persist_session_fct: Callable | None = None,
        scope: str = SCOPE_READ_ONLY,
    ) -> WSAPISession:
        data = {
            "grant_type": "password",
            "username": username,
            "password": password,
            "skip_provision": "true",
            "scope": scope,
            "client_id": self.session.client_id,
            "otp_claim": None,
        }

        headers = {
            "x-wealthsimple-client": "@wealthsimple/wealthsimple",
            "x-ws-profile": "undefined",
        }

        if otp_answer:
            headers["x-wealthsimple-otp"] = f"{otp_answer};remember=true"

        # Send the POST request for token
        response_data = self.send_post(
            url=f"{self.OAUTH_BASE_URL}/token", data=data, headers=headers
        )

        if (
            "error" in response_data
            and response_data["error"] == "invalid_grant"
            and otp_answer is None
        ):
            raise OTPRequiredException("2FA code required")

        if "error" in response_data:
            raise LoginFailedException("Login failed", response_data)

        # Update the session with the tokens
        self.session.access_token = response_data["access_token"]
        self.session.refresh_token = response_data["refresh_token"]

        # Persist the session if a persist function is provided
        if persist_session_fct:
            if len(signature(persist_session_fct).parameters) == 2:
                persist_session_fct(self.session.to_json(), username)
            else:
                persist_session_fct(self.session.to_json())

        return self.session

    def do_graphql_query(
        self,
        query_name: str,
        variables: dict,
        data_response_path: str,
        expect_type: str,
        filter_fn: Callable[[Any], bool] | None = None,
        *,
        load_all_pages: bool = False,
    ):
        query = {
            "operationName": query_name,
            "query": GRAPHQL_QUERIES[query_name],
            "variables": variables,
        }

        headers = {
            "x-ws-profile": "trade",
            "x-ws-api-version": self.GRAPHQL_VERSION,
            "x-ws-locale": "en-CA",
            "x-platform-os": "web",
        }

        response_data = self.send_post(
            url=self.GRAPHQL_URL, data=query, headers=headers
        )

        if "data" not in response_data:
            raise WSApiException(f"GraphQL query failed: {query_name}", response_data)

        data = response_data["data"]

        end_cursor = None

        # Access the nested data using the data_response_path
        for key in data_response_path.split("."):
            if key not in data:
                raise WSApiException(
                    f"GraphQL query failed: {query_name}", response_data
                )
            data = data[key]
            if (
                isinstance(data, dict)
                and "pageInfo" in data
                and isinstance(data["pageInfo"], dict)
                and data["pageInfo"].get("hasNextPage")
                and "endCursor" in data["pageInfo"]
            ):
                end_cursor = data["pageInfo"].get("endCursor")

        # Ensure the data type matches the expected one (either array or object)
        if (expect_type == "array" and not isinstance(data, list)) or (
            expect_type == "object" and not isinstance(data, dict)
        ):
            raise WSApiException(f"GraphQL query failed: {query_name}", response_data)

        # noinspection PyUnboundLocalVariable
        if key == "edges":
            data = [edge["node"] for edge in data]

        if filter_fn:
            data = list(filter(filter_fn, data))

        if load_all_pages:
            if expect_type != "array":
                raise UnexpectedException(
                    "Can't load all pages for GraphQL queries that do not return arrays"
                )
            if end_cursor:
                variables["cursor"] = end_cursor
                more_data = self.do_graphql_query(
                    query_name,
                    variables,
                    data_response_path,
                    expect_type,
                    filter_fn,
                    load_all_pages=True,
                )
                if isinstance(data, list) and isinstance(more_data, list):
                    data += more_data

        return data

    def get_token_info(self):
        if not self.session.token_info:
            headers = {"x-wealthsimple-client": "@wealthsimple/wealthsimple"}
            response = self.send_get(
                self.OAUTH_BASE_URL + "/token/info", headers=headers
            )
            self.session.token_info = response
        return self.session.token_info

    @staticmethod
    def login(
        username: str,
        password: str,
        otp_answer: str | None = None,
        persist_session_fct: Callable | None = None,
        scope: str = SCOPE_READ_ONLY,
    ) -> WSAPISession:
        """Login to Wealthsimple API and return a session object.

        Args:
            username (str): The username of the Wealthsimple account.
            password (str): The password of the Wealthsimple account.
            otp_answer (str, optional): The answer to the 2FA code. Defaults to None.
            persist_session_fct (callable, optional): A function to call to persist the session. Defaults to None.
            scope (str, optional): The OAuth scope for the session. Defaults to SCOPE_READ_ONLY.

        Returns:
            WSAPISession: The session object.

        Raises:
            LoginFailedException: If the login fails.
            OTPRequiredException: If 2FA code is required.
        """
        ws = WealthsimpleAPI()
        return ws.login_internal(
            username, password, otp_answer, persist_session_fct, scope
        )

    @staticmethod
    def from_token(
        sess: WSAPISession,
        persist_session_fct: Callable | None = None,
        username: str | None = None,
    ):
        ws = WealthsimpleAPI(sess)
        ws.check_oauth_token(persist_session_fct, username)
        return ws


class WealthsimpleAPI(WealthsimpleAPIBase):
    def __init__(self, sess: WSAPISession | None = None) -> None:
        super().__init__(sess)
        self.account_cache = {}

    def get_accounts(self, open_only=True, use_cache=True):
        cache_key = "open" if open_only else "all"
        if not use_cache or cache_key not in self.account_cache:
            filter_fn = (lambda acc: acc.get("status") == "open") if open_only else None

            accounts = self.do_graphql_query(
                "FetchAllAccountFinancials",
                {
                    "pageSize": 25,
                    "identityId": self.get_token_info().get("identity_canonical_id"),
                },
                "identity.accounts.edges",
                "array",
                filter_fn=filter_fn,
                load_all_pages=True,
            )
            for account in accounts:
                format_account_description(account)
            self.account_cache[cache_key] = accounts
        return self.account_cache[cache_key]

    def get_account_balances(self, account_id):
        accounts = self.do_graphql_query(
            "FetchAccountsWithBalance",
            {
                "type": "TRADING",
                "ids": [account_id],
            },
            "accounts",
            "array",
        )

        # Extracting balances and returning them in a dictionary
        balances = {}
        for account in accounts[0]["custodianAccounts"]:
            for balance in account["financials"]["balance"]:
                security = balance["securityId"]
                if security not in {"sec-c-cad", "sec-c-usd"}:
                    security = self.security_id_to_symbol(security)
                balances[security] = balance["quantity"]

        return balances

    def get_account_historical_financials(
        self,
        account_id: str,
        currency: str = "CAD",
        start_date=None,
        end_date=None,
        resolution="WEEKLY",
        first=None,
        cursor=None,
    ):
        return self.do_graphql_query(
            "FetchAccountHistoricalFinancials",
            {
                "id": account_id,
                "currency": currency,
                "startDate": start_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                if start_date
                else None,
                "endDate": end_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                if end_date
                else None,
                "resolution": resolution,
                "first": first,
                "cursor": cursor,
            },
            "account.financials.historicalDaily.edges",
            "array",
        )

    def get_identity_historical_financials(
        self,
        account_ids=None,
        currency: str = "CAD",
        start_date=None,
        end_date=None,
        first=None,
        cursor=None,
    ):
        return self.do_graphql_query(
            "FetchIdentityHistoricalFinancials",
            {
                "identityId": self.get_token_info().get("identity_canonical_id"),
                "currency": currency,
                "startDate": start_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                if start_date
                else None,
                "endDate": end_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                if end_date
                else None,
                "first": first,
                "cursor": cursor,
                "accountIds": account_ids or [],
            },
            "identity.financials.historicalDaily.edges",
            "array",
        )

    def get_activities(
        self,
        account_id: str | list[str],
        how_many: int = 50,
        order_by: str = "OCCURRED_AT_DESC",
        ignore_rejected: bool = True,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        load_all: bool = False,
    ) -> list[Any]:
        """Retrieve activities for a specific account or list of accounts.

        Args:
            account_id (str | list[str]): The account ID or list of account IDs to retrieve activities for.
            how_many (int): The maximum number of activities to retrieve.
            order_by (str): The order in which to sort the activities.
            ignore_rejected (bool): Whether to ignore rejected or cancelled activities.
            start_date (datetime, optional): The start date for filtering activities.
            end_date (datetime, optional): The end date for filtering activities.
            load_all (bool): Whether to load all pages of activities.

        Returns:
            list[Any]: A list of activity objects.

        Raises:
            WSApiException: If the response format is unexpected.
        """
        if isinstance(account_id, str):
            account_id = [account_id]
        # Calculate the end date for the condition
        end_date = (
            end_date
            if end_date
            else datetime.now()
            + timedelta(hours=23, minutes=59, seconds=59, milliseconds=999)
        )

        # Filter function to ignore rejected/cancelled/expired activities
        def filter_fn(activity):
            act_type = (activity.get("type", "") or "").upper()
            status = (activity.get("status", "") or "").lower()
            excluded_statuses = {"rejected", "cancelled", "expired"}
            is_excluded = any(s in status for s in excluded_statuses)
            return act_type != "LEGACY_TRANSFER" and (
                not ignore_rejected or status == "" or not is_excluded
            )

        activities = self.do_graphql_query(
            "FetchActivityFeedItems",
            {
                "orderBy": order_by,
                "first": how_many,
                "condition": {
                    "startDate": start_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                    if start_date
                    else None,
                    "endDate": end_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    "accountIds": account_id,
                },
            },
            "activityFeedItems.edges",
            "array",
            filter_fn=filter_fn,
            load_all_pages=load_all,
        )

        if not isinstance(activities, list):
            raise WSApiException(
                f"Unexpected response format: {self.get_activities.__name__}",
                activities,
            )
        for act in activities:
            format_activity_description(act, self)

        return activities

    def security_id_to_symbol(self, security_id: str) -> str:
        security_symbol = f"[{security_id}]"
        if self.security_market_data_cache_getter:
            try:
                market_data = self.get_security_market_data(security_id)
                if isinstance(market_data, dict) and market_data.get("stock"):
                    stock = market_data["stock"]
                    security_symbol = f"{stock['primaryExchange']}:{stock['symbol']}"
            except WSApiException:
                # Some securities cannot be looked up (e.g., delisted or special securities)
                pass
        return security_symbol

    def get_etf_details(self, funding_id):
        return self.do_graphql_query(
            "FetchFundsTransfer",
            {"id": funding_id},
            "fundsTransfer",
            "object",
        )

    def get_transfer_details(self, transfer_id):
        return self.do_graphql_query(
            "FetchInstitutionalTransfer",
            {"id": transfer_id},
            "accountTransfer",
            "object",
        )

    def set_security_market_data_cache(
        self,
        security_market_data_cache_getter: Callable,
        security_market_data_cache_setter: Callable,
    ) -> None:
        self.security_market_data_cache_getter = security_market_data_cache_getter
        self.security_market_data_cache_setter = security_market_data_cache_setter

    def get_security_market_data(self, security_id: str, use_cache: bool = True):
        if (
            not self.security_market_data_cache_getter
            or not self.security_market_data_cache_setter
        ):
            use_cache = False

        if use_cache:
            cached_value = self.security_market_data_cache_getter(security_id)
            if cached_value:
                return cached_value

        value = self.do_graphql_query(
            "FetchSecurityMarketData",
            {"id": security_id},
            "security",
            "object",
        )

        if use_cache:
            value = self.security_market_data_cache_setter(security_id, value)

        return value

    def get_security_historical_quotes(self, security_id, time_range="1m"):
        # Fetch historical quotes for a security using GraphQL query
        return self.do_graphql_query(
            "FetchSecurityHistoricalQuotes",
            {
                "id": security_id,
                "timerange": time_range,
            },
            "security.historicalQuotes",
            "array",
        )

    def get_corporate_action_child_activities(self, activity_canonical_id):
        # Fetch details about a corporate action (eg. a split) using GraphQL query
        return self.do_graphql_query(
            "FetchCorporateActionChildActivities",
            {
                "activityCanonicalId": activity_canonical_id,
            },
            "corporateActionChildActivities.nodes",
            "array",
        )

    def get_statement_transactions(self, account_id: str, period: str) -> list[Any]:
        """Retrieve transactions from account monthly statement.

        Args:
            account_id (str): The account ID to retrieve transactions for.
            period (str): The statement start date in 'YYYY-MM-DD' format.
                For example, '2025-10-01' for October 2025 statement.

        Returns:
            list[Any]: A list of transactions.

        Raises:
            WSApiException: If the response format is unexpected.
        """
        statements = self.do_graphql_query(
            "FetchBrokerageMonthlyStatementTransactions",
            {
                "accountId": account_id,
                "period": period,
            },
            "brokerageMonthlyStatements",
            "array",
        )

        if isinstance(statements, list) and len(statements) > 0:
            statement = statements[0]
            data = statement.get("data") if "data" in statement else {}
            transactions = (
                data.get("currentTransactions") if "currentTransactions" in data else []
            )

        if not transactions:
            return []
        if not isinstance(transactions, list):
            raise WSApiException(
                f"Unexpected response format: {self.get_statement_transactions.__name__}",
                transactions,
            )

        return transactions

    def get_identity_positions(
        self, security_ids: list[str] | None, currency: str
    ) -> list[Any]:
        """Retrieve information on specific positions

        Args:
            security_ids: list of Wealthsimple security ids, None will return all owned securities
            currency: currency to return the amounts in (CAD or USD)

        Returns:
            list[Any]: a list of positions by account

        Raises:
            WSApiException: If the response format is unexpected.
        """
        positions = self.do_graphql_query(
            "FetchIdentityPositions",
            {
                "identityId": self.get_token_info().get("identity_canonical_id"),
                "currency": currency,
                "filter": {"securityIds": security_ids},
                "includeAccountData": True,
            },
            "identity.financials.current.positions.edges",
            "array",
        )

        if not isinstance(positions, list):
            raise WSApiException(
                f"Unexpected response format: {self.get_identity_positions.__name__}",
                positions,
            )

        return positions

    def get_creditcard_account(self, credit_card_account_id: str) -> Any:
        account = self.do_graphql_query(
            "FetchCreditCardAccount",
            {
                "id": credit_card_account_id,
            },
            "creditCardAccount",
            "object",
        )

        return account
