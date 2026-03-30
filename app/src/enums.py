import enum

class UserStatus(enum.Enum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"

class JWTTokenStatus(enum.Enum):
    EXPIRED = "AUTH_TOKEN_EXPIRED"
    INVALID = "AUTH_TOKEN_INVALID"
    REUSED = "AUTH_REUSE_DETECTED"
    REVOKED = "AUTH_REVOKED"

class ErrorResponseCode(enum.Enum):
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    EMAIL_NOT_VERIFIED = "EMAIL_NOT_VERIFIED"