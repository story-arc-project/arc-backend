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
ALLOWED_UPLOAD_CONTENT_TYPE = [
    "application/pdf",
    "image/png",
    "image/jpeg"
] # MIME type

# Redis configurations
REDIS_HOST = "redis"
REDIS_PORT = 6379

ADMIN_PAGE_NOT_ALLOWED = "Admin page not allowed"

SUPPORT_EMAIL = "storyarc.org@gmail.com"