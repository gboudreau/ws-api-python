"""Formatting functions for human-readable descriptions."""

# Mapping of account types to human-readable descriptions
_ACCOUNT_TYPE_DESCRIPTIONS = {
    "SELF_DIRECTED_RRSP": "RRSP: self-directed",
    "MANAGED_RRSP": "RRSP: managed",
    "SELF_DIRECTED_SPOUSAL_RRSP": "RRSP: self-directed spousal",
    "SELF_DIRECTED_TFSA": "TFSA: self-directed",
    "MANAGED_TFSA": "TFSA: managed",
    "SELF_DIRECTED_FHSA": "FHSA: self-directed",
    "MANAGED_FHSA": "FHSA: managed",
    "SELF_DIRECTED_NON_REGISTERED": "Non-registered: self-directed",
    "SELF_DIRECTED_JOINT_NON_REGISTERED": "Non-registered: self-directed - joint",
    "SELF_DIRECTED_NON_REGISTERED_MARGIN": "Non-registered: self-directed margin",
    "MANAGED_JOINT": "Non-registered: managed - joint",
    "SELF_DIRECTED_CRYPTO": "Crypto",
    "SELF_DIRECTED_RRIF": "RRIF: self-directed",
    "SELF_DIRECTED_SPOUSAL_RRIF": "RRIF: self-directed spousal",
    "CREDIT_CARD": "Credit card",
    "SELF_DIRECTED_LIRA": "LIRA: self-directed",
}


def format_account_description(account: dict) -> None:
    """Add human-readable description to an account dict.

    Args:
        account: Account dictionary to modify in place.
    """
    account["number"] = account["id"]
    # This is the account number visible in the WS app:
    for ca in account["custodianAccounts"]:
        if ca["branch"] in ("WS", "TR") and ca["status"] == "open":
            account["number"] = ca["id"]

    if account.get("nickname"):
        account["description"] = account["nickname"]
        return

    account_type = account["unifiedAccountType"]

    # Special case: CASH depends on owner configuration
    if account_type == "CASH":
        account["description"] = (
            "Cash: joint"
            if account["accountOwnerConfiguration"] == "MULTI_OWNER"
            else "Cash"
        )
    # Special case: MANAGED_NON_REGISTERED depends on features
    elif account_type == "MANAGED_NON_REGISTERED":
        features = {f["name"] for f in account["accountFeatures"]}
        if "PRIVATE_CREDIT" in features:
            account["description"] = "Non-registered: managed - private credit"
        elif "PRIVATE_EQUITY" in features:
            account["description"] = "Non-registered: managed - private equity"
        else:
            account["description"] = account_type
    # Simple lookup for all other types
    else:
        account["description"] = _ACCOUNT_TYPE_DESCRIPTIONS.get(
            account_type, account_type
        )


def _format_institutional_transfer(act: dict, api_context) -> bool:
    """Format description for institutional transfer activities.

    Args:
        act: Activity dictionary to modify in place.
        api_context: API context object.

    Returns:
        True if this was an institutional transfer and was handled, False otherwise.
    """
    if act["type"] != "INSTITUTIONAL_TRANSFER_INTENT":
        return False

    if act["subType"] == "TRANSFER_IN":
        details = api_context.get_transfer_details(act["externalCanonicalId"])
        verb = ""
        client_account_type = ""
        institution_name = ""
        redacted_account_number = ""
        if isinstance(details, dict):
            verb = details["transferType"].replace("_", "-").capitalize()
            client_account_type = details["clientAccountType"].upper()
            institution_name = details["institutionName"]
            redacted_account_number = details["redactedInstitutionAccountNumber"]
        act["description"] = (
            f"Institutional transfer: {verb} {client_account_type} "
            f"account transfer from {institution_name} "
            f"****{redacted_account_number}"
        )
        return True

    if act["subType"] == "TRANSFER_OUT":
        act["description"] = (
            f"Institutional transfer: transfer to {act['institutionName']}"
        )
        return True

    return False


def _format_corporate_action_subdivision(act: dict, api_context) -> bool:
    """Format description for corporate action subdivision activities.

    Args:
        act: Activity dictionary to modify in place.
        api_context: API context object.

    Returns:
        True if this was a subdivision activity and was handled, False otherwise.
    """
    if not (act["type"] == "CORPORATE_ACTION" and act["subType"] == "SUBDIVISION"):
        return False

    child_activities = api_context.get_corporate_action_child_activities(
        act["canonicalId"]
    )
    held_activity = next(
        (
            activity
            for activity in child_activities
            if activity["entitlementType"] == "HOLD"
        ),
        None,
    )
    receive_activity = next(
        (
            activity
            for activity in child_activities
            if activity["entitlementType"] == "RECEIVE"
        ),
        None,
    )
    if held_activity and receive_activity:
        held_shares: float = float(held_activity["quantity"])
        received_shares: float = float(receive_activity["quantity"])
        total_shares: float = held_shares + received_shares
        act["description"] = (
            f"Subdivision: {held_shares} -> {total_shares} shares of {act['assetSymbol']}"
        )
    else:
        received_shares: float = float(act["amount"])
        act["description"] = (
            f"Subdivision: Received {received_shares} new shares of {act['assetSymbol']}"
        )

    if act["currency"] is None:
        security = api_context.get_security_market_data(act["securityId"])
        if security and isinstance(security, dict):
            fundamentals = security.get("fundamentals")
            if fundamentals and isinstance(fundamentals, dict):
                act["currency"] = fundamentals.get("currency")

    return True


def _format_credit_card_description(act: dict) -> str | None:
    """Format description for credit card activities.

    Args:
        act: Activity dictionary.

    Returns:
        Formatted description string, or None if not a credit card activity.
    """
    if act["type"] == "CREDIT_CARD" and act["subType"] == "PURCHASE":
        merchant = act["spendMerchant"]
        # Posted purchase transactions have status = settled
        status = "(Pending) " if act["status"] == "authorized" else ""
        return f"{status}Credit card purchase: {merchant}"

    if act["type"] == "CREDIT_CARD" and act["subType"] == "HOLD":
        merchant = act["spendMerchant"]
        # Posted return transactions have subType = REFUND and status = settled
        status = "(Pending) " if act["status"] == "authorized" else ""
        return f"{status}Credit card refund: {merchant}"

    if act["type"] == "CREDIT_CARD" and act["subType"] == "REFUND":
        merchant = act["spendMerchant"]
        return f"Credit card refund: {merchant}"

    if (act["type"] == "CREDIT_CARD" and act["subType"] == "PAYMENT") or act[
        "type"
    ] == "CREDIT_CARD_PAYMENT":
        return "Credit card payment"

    return None


def format_activity_description(act: dict, api_context) -> None:
    """Add human-readable description to an activity dict.

    Args:
        act: Activity dictionary to modify in place.
        api_context: API context object providing methods like:
            - get_accounts(open_only: bool)
            - security_id_to_symbol(security_id: str)
            - get_corporate_action_child_activities(activity_canonical_id: str)
            - get_security_market_data(security_id: str)
            - get_etf_details(funding_id: str)
            - get_transfer_details(transfer_id: str)
    """
    act["description"] = f"{act['type']}: {act['subType']}"

    if act["type"] == "INTERNAL_TRANSFER" or act["type"] == "ASSET_MOVEMENT":
        accounts = api_context.get_accounts(False)
        matching = [acc for acc in accounts if acc["id"] == act["opposingAccountId"]]
        target_account = matching.pop() if matching else None
        account_description = (
            f"{target_account['description']} ({target_account['number']})"
            if target_account
            else act["opposingAccountId"]
        )
        direction = "to" if act["subType"] == "SOURCE" else "from"
        act["description"] = (
            f"Money transfer: {direction} Wealthsimple {account_description}"
        )

    elif act["type"] in ["DIY_BUY", "DIY_SELL", "MANAGED_BUY", "MANAGED_SELL"]:
        if "MANAGED" in act["type"]:
            verb = "Managed transaction"
        else:
            verb = act["subType"].replace("_", " ").capitalize()
        action = (
            "buy"
            if act["type"] == "DIY_BUY" or act["type"] == "MANAGED_BUY"
            else "sell"
        )
        security = api_context.security_id_to_symbol(act["securityId"])
        if act["assetQuantity"] is None:
            act["description"] = f"{verb}: {action} TBD"
        else:
            act["description"] = (
                f"{verb}: {action} {float(act['assetQuantity'])} x "
                f"{security} @ {float(act['amount']) / float(act['assetQuantity'])}"
            )

    elif _format_corporate_action_subdivision(act, api_context):
        pass  # Handled by helper function

    elif act["type"] in ["DEPOSIT", "WITHDRAWAL"] and act["subType"] in [
        "E_TRANSFER",
        "E_TRANSFER_FUNDING",
    ]:
        direction = "from" if act["type"] == "DEPOSIT" else "to"
        act["description"] = (
            f"Deposit: Interac e-transfer {direction} {act['eTransferName']} {act['eTransferEmail']}"
        )

    elif act["type"] == "DEPOSIT" and act["subType"] == "PAYMENT_CARD_TRANSACTION":
        type_ = act["type"].lower().capitalize()
        act["description"] = f"{type_}: Debit card funding"

    elif act["subType"] == "EFT":
        details = api_context.get_etf_details(act["externalCanonicalId"])
        type_ = act["type"].lower().capitalize()
        direction = "from" if act["type"] == "DEPOSIT" else "to"
        prop = "source" if act["type"] == "DEPOSIT" else "destination"
        bank_account_info = {}
        if isinstance(details, dict):
            bank_account_info = details.get(prop, {})
        bank_account = {}
        if isinstance(bank_account_info, dict):
            bank_account = bank_account_info.get("bankAccount", {})
        nickname = bank_account.get("nickname")
        account_number = bank_account.get("accountNumber")
        if not nickname:
            nickname = bank_account.get("accountName")
        act["description"] = f"{type_}: EFT {direction} {nickname} {account_number}"

    elif act["type"] == "REFUND" and act["subType"] == "TRANSFER_FEE_REFUND":
        act["description"] = "Reimbursement: account transfer fee"

    elif _format_institutional_transfer(act, api_context):
        pass  # Handled by helper function
    elif act["type"] == "INTEREST":
        if act["subType"] == "FPL_INTEREST":
            act["description"] = "Stock Lending Earnings"
        else:
            act["description"] = "Interest"

    elif act["type"] == "DIVIDEND":
        security = api_context.security_id_to_symbol(act["securityId"])
        act["description"] = f"Dividend: {security}"

    elif act["type"] == "FUNDS_CONVERSION":
        act["description"] = (
            f"Funds converted: {act['currency']} from {'USD' if act['currency'] == 'CAD' else 'CAD'}"
        )

    elif act["type"] == "NON_RESIDENT_TAX":
        act["description"] = "Non-resident tax"

    # Refs:
    #   https://www.payments.ca/payment-resources/iso-20022/automatic-funds-transfer
    #   https://www.payments.ca/compelling-new-evidence-strong-link-between-aft-and-canadas-cheque-decline
    # 2nd ref states: "AFTs are electronic direct credit or direct debit transactions, commonly known in Canada as direct deposits or pre-authorized debits (PADs)."
    elif act["type"] in ("DEPOSIT", "WITHDRAWAL") and act["subType"] == "AFT":
        type_ = "Direct deposit" if act["type"] == "DEPOSIT" else "Pre-authorized debit"
        direction = "from" if type_ == "Direct deposit" else "to"
        institution = (
            act["aftOriginatorName"]
            if act["aftOriginatorName"]
            else act["externalCanonicalId"]
        )
        act["description"] = f"{type_}: {direction} {institution}"

    elif act["type"] == "WITHDRAWAL" and act["subType"] == "BILL_PAY":
        type_ = act["type"].capitalize()
        name = act["billPayPayeeNickname"]
        if not name:
            name = act["billPayCompanyName"]
        number = act["redactedExternalAccountNumber"]
        act["description"] = f"{type_}: Bill pay {name} {number}"

    elif act["type"] == "P2P_PAYMENT" and act["subType"] in (
        "SEND",
        "SEND_RECEIVED",
    ):
        direction = "sent to" if act["subType"] == "SEND" else "received from"
        p2p_handle = act["p2pHandle"]
        act["description"] = f"Cash {direction} {p2p_handle}"

    elif act["type"] == "PROMOTION" and act["subType"] == "INCENTIVE_BONUS":
        type_ = act["type"].capitalize()
        subtype = act["subType"].replace("_", " ").capitalize()
        act["description"] = f"{type_}: {subtype}"

    elif act["type"] == "REFERRAL" and act["subType"] is None:
        type_ = act["type"].capitalize()
        act["description"] = f"{type_}"

    elif credit_card_desc := _format_credit_card_description(act):
        act["description"] = credit_card_desc

    elif act["type"] == "REIMBURSEMENT" and act["subType"] == "CASHBACK":
        program = (
            "- Visa Infinite"
            if act["rewardProgram"] == "CREDIT_CARD_VISA_INFINITE_REWARDS"
            else ""
        )
        act["description"] = f"Cash back {program}".rstrip()

    elif act["type"] == "SPEND" and act["subType"] == "PREPAID":
        merchant = act["spendMerchant"]
        act["description"] = f"Purchase: {merchant}"

    elif act["type"] == "INTEREST_CHARGE":
        if act["subType"] == "MARGIN_INTEREST":
            act["description"] = "Interest Charge: margin interest"
        else:
            act["description"] = "Interest Charge"

    elif act["type"] == "FEE" and act["subType"] == "MANAGEMENT_FEE":
        act["description"] = "Management fee"

    # TODO: Add other types as needed
