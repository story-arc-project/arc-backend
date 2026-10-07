from collections.abc import Mapping
from typing import Final, Literal, TypedDict

ACCESS_TOKEN_EXPIRE  = 15 # minutes
REFRESH_TOKEN_EXPIRE = 14 # days
JWT_ALG = "HS256"
VERIFICATION_CODE_EXPIRE = 10 # minutes
VERIFICATION_MAX_ATTEMPTS = 5
SHOW_REMAINING_VERIFICATION_ATTEMPTS = False # boolean
ACCESS_TOKEN_KEY = "accessToken"
REFRESH_TOKEN_KEY = "refreshToken"
LOGIN_REDIRECT_ENDPOINT_PREFIX = "/callback/"

# Retry limits
LOGIN_MAX_RETRY_COUNT = 5
LOGIN_RETRY_COOLDOWN = 10 # minutes
VERIFY_EMAIL_MAX_RETRY_COUNT = 5
VERIFY_EMAIL_RETRY_COOLDOWN = 10 # minutes

# File configurations
UPLOAD_EXPIRES_IN = 300 # seconds
DOWNLOAD_EXPIRES_IN = 3600 # seconds
ALLOWED_UPLOAD_CONTENT_SIZE = 50 # MB
# ALLOWED_UPLOAD_CONTENT_TYPE = [
#     "application/pdf",
#     "image/png",
#     "image/jpeg"
# ] # MIME type

# Redis configurations
REDIS_HOST = "redis"
REDIS_PORT = 6379

ADMIN_PAGE_NOT_ALLOWED = "Admin page not allowed"

SUPPORT_EMAIL = "storyarc.org@gmail.com"

# Credit policies
type CreditPolicyVersion = Literal[
    "2026-09-26-v1",
]
type CreditFeature = Literal[
    "individual",
    "comprehensive",
    "keyword",
    "resume",
    "cover_letter",
]
type CreditPolicy = Mapping[CreditFeature, int]
CURRENT_CREDIT_POLICY_VERSION: Final[CreditPolicyVersion] = "2026-09-26-v1"
CREDIT_POLICY_VERSIONS: Final[Mapping[CreditPolicyVersion, CreditPolicy]] = {
    "2026-09-26-v1": {
        "individual": 0,
        "comprehensive": 2,
        "keyword": 2,
        "resume": 3,
        "cover_letter": 3,
    },
}
class CreditPackage(TypedDict):
    id: str
    name: str
    credits: int
    price_krw: int
PACKAGES: Final[list[CreditPackage]] = [
    { "id": "lite", "name": "Lite", "credits": 20, "price_krw": 4900 },
    { "id": "basic", "name": "Basic", "credits": 50, "price_krw": 9900 },
    { "id": "pro", "name": "Pro", "credits": 120, "price_krw": 19900 }
]