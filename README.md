Unofficial Wealthsimple API Library for Python
==============================================

This library allows you to access your own Wealthsimple account using the Wealthsimple (GraphQL) API.

> **Python 3.10+ required**

Features
--------

- Retrieve all accounts (RRSP, TFSA, FHSA, cash, margin, crypto, credit card)
- Get account balances and positions
- Fetch historical performance (net value, deposits, gains)
- Access transaction/activity history
- Search securities and get market data
- Historical price quotes
- Handle 2FA (TOTP) authentication
- Automatic session refresh
- Optional security data caching

Installation
------------

```bash
uv add ws-api
# or
pip install ws-api
```

Upgrading
---------

If you are updating from 0.35 or less, to 0.36 or more, the `requests` dependency has been replaced with `curl_cffi`.  
If you installed using `uv` or `pip` (and you update using either), they will take care of that for you.

### Basic Example

```python
from ws_api import WealthsimpleAPI

# Login (will prompt for username/password/TOTP); notify the user if Wealthsimple requires mobile approval.
session = WealthsimpleAPI.login(
    username="you@example.com",
    password="yourpassword",
    approval_callback=lambda: print("Approve the login in the Wealthsimple mobile app."),
)
ws = WealthsimpleAPI.from_token(session)

# Get your accounts
accounts = ws.get_accounts()
for account in accounts:
    print(f"{account['description']}: {account['number']}")
```

When mobile approval is required, login polls for up to two minutes and retries
automatically after approval. Without an approval callback, it emits a warning.
If a TOTP code is required, login raises `OTPRequiredException`; callers must
obtain the code and retry with `otp_answer`. See the full example below.

### Full Example

Note: You'll need the keyring package to run the code below. Install with: `uv add keyring` (or `pip install keyring`)

See [tests/test_full_example.py](https://github.com/gboudreau/ws-api-python/blob/main/tests/test_full_example.py)


Projects Using It
-----------------

- [wealthgrabber](https://github.com/ebastos/wealthgrabber) - Wealthsimple portfolio analytics
