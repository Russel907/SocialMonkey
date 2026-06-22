import os
import logging
import requests
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

MESSAGECENTRAL_BASE = os.environ.get("MESSAGECENTRAL_BASE", "https://cpaas.messagecentral.com")
MESSAGECENTRAL_CUSTOMER_ID = os.environ.get("MESSAGECENTRAL_CUSTOMER_ID")
MESSAGECENTRAL_BASE64_KEY = os.environ.get("MESSAGECENTRAL_BASE64_KEY")
MESSAGECENTRAL_DEFAULT_COUNTRY = os.environ.get("MESSAGECENTRAL_COUNTRY_CODE", "91")

logger.info("MSGCENT_CUSTOMER=%s MSGCENT_KEY_PRESENT=%s",
            MESSAGECENTRAL_CUSTOMER_ID,
            bool(MESSAGECENTRAL_BASE64_KEY))


def _get_auth_token(country=MESSAGECENTRAL_DEFAULT_COUNTRY, scope="NEW", email=None, timeout=10):
    if not MESSAGECENTRAL_CUSTOMER_ID or not MESSAGECENTRAL_BASE64_KEY:
        logger.error("MessageCentral credentials missing (CUSTOMER_ID/BASE64_KEY)")
        return False, {"error": "missing_credentials"}

    path = "/auth/v1/authentication/token"
    params = {
        "customerId": MESSAGECENTRAL_CUSTOMER_ID,
        "key": MESSAGECENTRAL_BASE64_KEY,
        "scope": scope,
        "country": country,
    }
    if email:
        params["email"] = email

    url = f"{MESSAGECENTRAL_BASE}{path}?{urlencode(params)}"
    try:
        resp = requests.get(url, headers={"accept": "*/*"}, timeout=timeout)
    except requests.RequestException as exc:
        logger.exception("Network error while requesting auth token")
        return False, {"error": "network", "desc": str(exc)}

    if resp.status_code != 200:
        return False, {"status": resp.status_code, "body": resp.text}

    try:
        j = resp.json()
    except ValueError:
        return False, {"error": "invalid_json", "raw": resp.text}

    token = j.get("token")
    if not token:
        return False, {"error": "no_token_in_response", "body": j}

    return True, token


def send_otp_via_messagecentral(mobile_number: str, message: str, country_code=MESSAGECENTRAL_DEFAULT_COUNTRY, timeout=10):
    ok, token_or_err = _get_auth_token(country=country_code)
    if not ok:
        return False, token_or_err

    auth_token = token_or_err
    path = "/verification/v3/send"
    params = {
        "countryCode": country_code,
        "flowType": "SMS",
        "mobileNumber": mobile_number,
    }
    url = f"{MESSAGECENTRAL_BASE}{path}?{urlencode(params)}"
    headers = {
        "authToken": auth_token,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {"message": message}

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        logger.exception("Network error while sending OTP to %s", mobile_number)
        return False, {"error": "network", "desc": str(exc)}

    if resp.status_code == 200:
        try:
            return True, resp.json()
        except ValueError:
            return True, {"raw": resp.text}
    else:
        return False, {"status": resp.status_code, "body": resp.text}
