import enum

class UserStatus(enum.Enum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    BANNED = "banned"
    DELETED = "deleted"

class JWTTokenStatus(enum.Enum):
    EXPIRED = "AUTH_TOKEN_EXPIRED"
    INVALID = "AUTH_TOKEN_INVALID"
    REUSED = "AUTH_REUSE_DETECTED"
    REVOKED = "AUTH_REVOKED"