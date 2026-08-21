"""
services/sms_service.py
সরাসরি অভিভাবকের ফোনের SIM-এ SMS পাঠানোর লজিক (Telegram notification-এর
পাশাপাশি, বিকল্প হিসেবে নয়)। একাধিক BD SMS Gateway সাপোর্ট করে — .env-এ
SMS_PROVIDER দিয়ে বেছে নেওয়া যায়। ব্যর্থ হলে silently False রিটার্ন করে,
exception raise করে না — যাতে SMS ব্যর্থতা কখনও Attendance flow আটকে না দেয়।
"""
import httpx

from config import SMS_API_KEY, SMS_SENDER_ID, SMS_PROVIDER, logger

_TIMEOUT = httpx.Timeout(10.0)


def normalize_bd_phone(phone: str) -> str | None:
    """
    যেকোনো ফরম্যাটের BD নম্বরকে 8801XXXXXXXXX ফরম্যাটে আনে।
    অবৈধ মনে হলে None রিটার্ন করে।
    """
    if not phone:
        return None
    digits = "".join(ch for ch in phone if ch.isdigit())
    if digits.startswith("880") and len(digits) == 13:
        return digits
    if digits.startswith("01") and len(digits) == 11:
        return "88" + digits
    if digits.startswith("1") and len(digits) == 10:
        return "880" + digits
    return None


async def _send_bulksmsbd(phone: str, message: str) -> tuple[bool, str]:
    url = "http://bulksmsbd.net/api/smsapi"
    params = {
        "api_key": SMS_API_KEY,
        "type": "text",
        "number": phone,
        "senderid": SMS_SENDER_ID,
        "message": message,
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        body = resp.text.strip()
        # bulksmsbd সফল হলে response_code=202 এর মতো কিছু বা JSON রিটার্ন করে
        if '"response_code":202' in body or body.startswith("1902") or "SMS SUBMITTED" in body.upper():
            return True, body
        return False, body


async def _send_alphasms(phone: str, message: str) -> tuple[bool, str]:
    url = "https://api.sms.net.bd/sendsms"
    payload = {"api_key": SMS_API_KEY, "msg": message, "to": phone}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(url, data=payload)
        resp.raise_for_status()
        body = resp.text.strip()
        if '"error":false' in body.lower() or '"status":"success"' in body.lower():
            return True, body
        return False, body


_PROVIDERS = {
    "bulksmsbd": _send_bulksmsbd,
    "alphasms": _send_alphasms,
}


async def send_sms(phone: str, message: str) -> bool:
    """
    Guardian-এর ফোনে সরাসরি SMS পাঠায়। কনফিগার করা না থাকলে বা নম্বর অবৈধ
    হলে False রিটার্ন করে, কোনো exception ছুঁড়ে না।
    """
    if not SMS_API_KEY:
        logger.warning("SMS পাঠানো যায়নি: SMS_API_KEY .env-এ সেট করা নেই।")
        return False

    normalized = normalize_bd_phone(phone)
    if not normalized:
        logger.warning(f"SMS পাঠানো যায়নি: অবৈধ ফোন নম্বর '{phone}'।")
        return False

    sender = _PROVIDERS.get(SMS_PROVIDER)
    if not sender:
        logger.warning(f"SMS পাঠানো যায়নি: অজানা SMS_PROVIDER '{SMS_PROVIDER}'।")
        return False

    try:
        ok, detail = await sender(normalized, message)
        if not ok:
            logger.warning(f"SMS gateway ({SMS_PROVIDER}) ব্যর্থতা জানালো: {detail}")
        return ok
    except httpx.HTTPError as e:
        logger.warning(f"SMS পাঠাতে গিয়ে নেটওয়ার্ক error ({SMS_PROVIDER}): {e}")
        return False
    except Exception as e:  # pragma: no cover - কোনো অবস্থাতেই attendance flow আটকাবে না
        logger.warning(f"SMS পাঠাতে গিয়ে অপ্রত্যাশিত error ({SMS_PROVIDER}): {e}")
        return False
