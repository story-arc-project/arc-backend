import enum

class EducationType(enum.Enum):
    SCHOOL_STUDENT = "초중고"
    UNIVERSITY = "대학생"
    GRADUATE = "대학원"
    ALUMNI = "졸업생"

class JWTTokenStatus(enum.Enum):
    EXPIRED = "AUTH_TOKEN_EXPIRED"
    INVALID = "AUTH_TOKEN_INVALID"
    REUSED = "AUTH_REUSE_DETECTED"
    REVOKED = "AUTH_REVOKED"