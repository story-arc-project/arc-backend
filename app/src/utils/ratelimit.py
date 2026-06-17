from pydantic import EmailStr

from src.api.models.base import ErrorResponse, ErrorResponseCode
from src.api.models.exc import AppException
from src.db.red import increment_attempt, is_locked, clear as red_clear, set_lockout

class RateLimiter:
    def __init__(self, ip: str | None, email: EmailStr, key: str, cooldown_min: int, max_retry: int, custom_locked_exception: ErrorResponse | None = None, init: bool = False):
        self.cooldown_min = cooldown_min
        self.max_retry = max_retry
        self.custom_locked_exception = custom_locked_exception
        self.keys = [f"{key}:email:{email}"]
        if ip is not None:
            self.keys.append(f"{key}:ip:{ip}")
        if init:
            for key in self.keys:
                red_clear(key)
        else:
            for key in self.keys:
                locked, ttl = is_locked(key)
                if locked:
                    raise AppException(
                        status_code = 429,
                        error = ErrorResponse(
                            code = ErrorResponseCode.ACCOUNT_LOCKED,
                            message = f"Too many attempts. Retry in {ttl}s."
                        ) if (self.custom_locked_exception is None) else self.custom_locked_exception
                    )
    def record_failure(self):
        current_attempts: dict[str, int] = {}
        for key in self.keys:
            count = increment_attempt(key, self.cooldown_min)
            if count is None:
                raise AppException(
                    status_code = 500,
                    error = ErrorResponse(
                        code = ErrorResponseCode.SERVER_ERROR,
                        message = "Lockdown attempt counter"
                    )
                )
            if count >= self.max_retry:
                set_lockout(key, self.cooldown_min)
                raise AppException(
                    status_code = 429,
                    error = ErrorResponse(
                        code = ErrorResponseCode.ACCOUNT_LOCKED,
                        message = f"Locked out for {self.cooldown_min} minutes."
                    ) if (self.custom_locked_exception is None) else self.custom_locked_exception
                )
            current_attempts[key.split(":")[-2]] = count
        return current_attempts
    def clear(self):
        for key in self.keys:
            red_clear(key)