Unofficial Wealthsimple API Library for Python
==============================================

This library allows you to access your own account using the Wealthsimple (GraphQL) API using Python.

Installation
------------

```bash
uv add ws-api
```

Usage
-----

Note: You'll need the keyring package to run the code below. Install with: `uv add keyring`

```python
from datetime import datetime
import json
import keyring
import os
import tempfile
from ws_api import WealthsimpleAPI, OTPRequiredException, LoginFailedException, WSAPISession

class WSApiTest:
    def main(self):
        # 1. Define a function that will be called when the session is created or updated. Persist the session to a safe place, like in the keyring
        keyring_service_name = "foo.bar"
        persist_session_fct = lambda sess, uname: keyring.set_password(f"{keyring_service_name}.{uname}", "session", sess)
        # The session contains tokens that can be used to empty your Wealthsimple account, so treat it with respect!
        # i.e. don't store it in a Git repository, or anywhere it can be accessed by others!

        # If you want, you can set a custom User-Agent for the requests to the WealthSimple API:
        WealthsimpleAPI.set_user_agent("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36")
    
        # 2. If it's the first time you run this, create a new session using the username & password (and TOTP answer, if needed). Do NOT save those infos in your code!
        username = input("Wealthsimple username (email): ")
        session = keyring.get_password(f"{keyring_service_name}.{username}", "session")
        if session:
            session = WSAPISession.from_json(session)
        if not session:
            username = None
            password = None
            otp_answer = None
            while True:
                try:
                    if not username:
                        username = input("Wealthsimple username (email): ")
                        session = keyring.get_password(f"{keyring_service_name}.{username}", "session")
                        if session:
                            session = WSAPISession.from_json(session)
                            break
                    if not password:
                        password = input("Password: ")
                    WealthsimpleAPI.login(username, password, otp_answer, persist_session_fct=persist_session_fct)
                    # The above will throw exceptions if login failed
                    # So we break (out of the login "while True" loop) on success:
                    session = WSAPISession.from_json(keyring.get_password(keyring_service_name, "session"))
                    break
                except OTPRequiredException:
                    otp_answer = input("TOTP code: ")
                except LoginFailedException:
                    print("Login failed. Try again.")
                    username = None
                    password = None
    
        # 3. Use the session object to instantiate the API object
        ws = WealthsimpleAPI.from_token(session, persist_session_fct, username)
        # persist_session_fct is needed here too, because the session may be updated if the access token expired, and thus this function will be called to save the new session
        
        # Optionally define functions to cache market data, if you want transactions' descriptions and accounts balances to show the security's symbol instead of its ID
        # eg. sec-s-e7947deb977341ff9f0ddcf13703e9a6 => TSX:XEQT
        def sec_info_getter_fn(ws_security_id: str):
            cache_file_path = os.path.join(tempfile.gettempdir(), f"ws-api-{ws_security_id}.json")
            if os.path.exists(cache_file_path):
                return json.load(open(cache_file_path, 'r'))
            return None
        def sec_info_setter_fn(ws_security_id: str, market_data: object):
            cache_file_path = os.path.join(tempfile.gettempdir(), f"ws-api-{ws_security_id}.json")
            # noinspection PyTypeChecker
            json.dump(market_data, open(cache_file_path, 'w'))
            return market_data
        ws.set_security_market_data_cache(sec_info_getter_fn, sec_info_setter_fn)
        
        # 4. Use the API object to access your WS accounts
        accounts = ws.get_accounts()

        print("All Accounts Historical Value & Gains:")
        historical_fins = ws.get_identity_historical_financials([a['id'] for a in accounts])
        for hf in historical_fins:
            value = float(hf['netLiquidationValueV2']['amount'])
            deposits = float(hf['netDepositsV2']['amount'])
            gains = value - deposits
            print(f"  - {hf['date']} = ${value:,.0f} - {deposits:,.0f} (deposits) = {gains:,.0f} (gains)")
        
        for account in accounts:
            print(f"Account: {account['description']} ({account['number']})")
            if account['description'] == account['unifiedAccountType']:
                # This is an "unknown" account, for which description is generic; please open an issue on https://github.com/gboudreau/ws-api-python/issues and include the following:
                print(f"    Unknown account: {account}")

            if account['currency'] == 'CAD':
                value = account['financials']['currentCombined']['netLiquidationValue']['amount']
                print(f"  Net worth: {value} {account['currency']}")    
            # Note: For USD accounts, value is the CAD value converted to USD
            # For USD accounts, only the balance & positions are relevant
    
            # Cash and positions balances
            balances = ws.get_account_balances(account['id'])
            cash_balance_key = 'sec-c-usd' if account['currency'] == 'USD' else 'sec-c-cad'
            cash_balance = float(balances.get(cash_balance_key, 0))
            print(f"  Available (cash) balance: {cash_balance} {account['currency']}")
    
            if len(balances) > 1:
                print("  Assets:")
                for security, bal in balances.items():
                    if security in ['sec-c-cad', 'sec-c-usd']:
                        continue
                    print(f"  - {security} x {bal}")
    
            print("  Historical Value & Gains:")
            historical_fins = ws.get_account_historical_financials(account['id'], account['currency'])            
            for hf in historical_fins:
                value = hf['netLiquidationValueV2']['cents'] / 100
                deposits = hf['netDepositsV2']['cents'] / 100
                gains = value - deposits
                print(f"  - {hf['date']} = ${value:,.0f} - {deposits:,.0f} (deposits) = {gains:,.0f} (gains)")
            
            # Fetch activities (transactions)
            acts = ws.get_activities(account['id'])
            if acts:
                print("  Transactions:")
                acts.reverse()  # Activities are sorted by OCCURRED_AT_DESC by default

                for act in acts:
                    if act['type'] == 'DIY_BUY':
                        act['amountSign'] = 'negative'
        
                    # Print transaction details
                    print(
                        f"  - [{datetime.strptime(act['occurredAt'].replace(':', ''), '%Y-%m-%dT%H%M%S.%f%z')}] [{act['canonicalId']}] {act['description']} "
                        f"{'+' if act['amountSign'] == 'positive' else '-'}{act['amount']} {act['currency']}")

                    if act['description'] == f"{act['type']}: {act['subType']}":
                        # This is an "unknown" transaction, for which description is generic; please open an issue on https://github.com/gboudreau/ws-api-python/issues and include the following:
                        print(f"    Unknown activity: {act}")
    
            print()

if __name__ == "__main__":
    WSApiTest().main()

```
