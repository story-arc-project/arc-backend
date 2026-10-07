from email.mime.multipart import MIMEMultipart
from unittest.mock import MagicMock
import re

from fastapi.testclient import TestClient
from pydantic import EmailStr

from src.api.models.consent import AGREEABLE_CONSENT_VERSIONS

def get_sent_mail(mock_mail: MagicMock):
    sent_mail: MIMEMultipart = mock_mail.send_message.call_args.args[0]
    for part in sent_mail.walk():
        if part.is_multipart():
            continue

        if part.get_content_type() in ("text/plain", "text/html"):
            return {
                "To": sent_mail["To"],
                "Subject": sent_mail["Subject"],
                "Content-Type": part.get_content_type(),
                "Body": part.get_payload(decode=True).decode(
                    part.get_content_charset() or "utf-8"
                )
            }
    return {
        "To": sent_mail["To"],
        "Subject": sent_mail["Subject"],
        "Content-Type": None,
        "Body": None
    }

def get_verification_code(mock_mail: MagicMock):
    email_received = get_sent_mail(mock_mail)
    email_content_type = email_received["Content-Type"]
    assert isinstance(email_content_type, str)
    is_email_html = email_content_type.startswith("text/html")
    regex = r">\s*(\d{6})\s*<" if is_email_html else r"인증번호:\s*(\d{6})"
    search_result = re.search(regex, email_received["Body"])
    assert search_result is not None, "Verification code not found in email body"
    code = search_result.group(1)
    return code

def generate_authenticated_user(client: TestClient, mock_mail: MagicMock, email: EmailStr, password: str):
    _ = client.post("/auth/signup", json={"email": email, "password": password})
    code = get_verification_code(mock_mail)
    response = client.post("/auth/verify-email", json={
        "email": email,
        "code": code
    })
    assert response.status_code == 200
    assert client.cookies.get("refreshToken") is not None
    assert client.cookies.get("accessToken") is not None

def onboard_user(authenticated_client: TestClient):
    response = authenticated_client.post("/auth/consent", json={
        "agreements": {
            "termsOfService": {"version": AGREEABLE_CONSENT_VERSIONS["termsOfService"], "granted": True},
            "privacyRequired": {"version": AGREEABLE_CONSENT_VERSIONS["privacyRequired"], "granted": True},
            "age14": {"granted": True},
            "personalizedService": {"version": AGREEABLE_CONSENT_VERSIONS["personalizedService"], "granted": True},
            "marketing": {"version": AGREEABLE_CONSENT_VERSIONS["marketing"], "granted": True},
        }
    })
    assert response.status_code == 200
    response = authenticated_client.post("/auth/onboarding", json={
        "name": "홍길동",
        "birth": "2001-01-01",
        "affiliation": "student",
        "school": "서울대학교",
        "department": "컴퓨터공학부",
        "company": None,
        "desiredRole": None,
        "affiliationDetail": None,
        "phone": "01000000000",
        "worry": ["진로", "이력"],
        "interest": ["컴퓨터", "AI"]
    })
    assert response.status_code == 200