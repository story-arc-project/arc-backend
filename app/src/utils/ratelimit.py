from fastapi import Depends, Request, Response
from fastapi_limiter.depends import RateLimiter as FastAPILimiter
from pydantic import EmailStr
from pydantic_settings import BaseSettings
from pyrate_limiter import Duration, Limiter, Rate
from typing import Annotated, Callable, Literal

from src.api.models.base import ErrorResponse, ErrorResponseCode
from src.api.models.exc import AppException
from src.db.red import increment_attempt, is_locked, clear as red_clear, set_lockout
from src.utils.auth import check_auth
from src.utils.token import AccessTokenPayload
from src.utils.req import get_ip

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

class AnalysisRateLimitSettings(BaseSettings):
    rate_limit_analysis_individual: int
    rate_limit_analysis_comprehensive: int
    rate_limit_analysis_keyword: int
    rate_limit_export_resume: int
    rate_limit_export_cover_letter: int

analysis_rate_limit_settings = AnalysisRateLimitSettings()

async def get_ip_identifier(request: Request):
    return f"ip:{get_ip(request)}"

async def analysis_rate_limit_callback(request: Request, response: Response):
    raise AppException(
        429,
        ErrorResponse(
            code=ErrorResponseCode.TOO_MANY_ATTEMPTS,
            message="Too many requests."
        )
    )

class UserRateLimiter:
    def __init__(
        self,
        limiter: Limiter,
        callback: Callable = analysis_rate_limit_callback,
        blocking: bool = False,
    ):
        self.limiter = limiter
        self.callback = callback
        self.blocking = blocking

    async def __call__(
        self,
        request: Request,
        response: Response,
        payload: Annotated[AccessTokenPayload, Depends(check_auth)]
    ):
        route = request.scope.get("route")
        path = getattr(route, "path", request.scope["path"])
        key = f"user:{payload.sub}:{request.method}:{path}"
        success = await self.limiter.try_acquire_async(key, blocking=self.blocking)
        if not success:
            return await self.callback(request, response)

analysis_rate_limiters: dict[Literal["individual", "comprehensive", "keyword", "resume", "cover_letter"], dict[Literal["user", "ip"], UserRateLimiter | FastAPILimiter]] = {
    "individual": {
        "user": UserRateLimiter(
            limiter=Limiter(Rate(analysis_rate_limit_settings.rate_limit_analysis_individual, Duration.HOUR))
        ),
        "ip": FastAPILimiter(
            limiter=Limiter(Rate(analysis_rate_limit_settings.rate_limit_analysis_individual, Duration.HOUR)),
            identifier=get_ip_identifier,
            callback=analysis_rate_limit_callback
        )
    },
    "comprehensive": {
        "user": UserRateLimiter(
            limiter=Limiter(Rate(analysis_rate_limit_settings.rate_limit_analysis_comprehensive, Duration.HOUR))
        ),
        "ip": FastAPILimiter(
            limiter=Limiter(Rate(analysis_rate_limit_settings.rate_limit_analysis_comprehensive, Duration.HOUR)),
            identifier=get_ip_identifier,
            callback=analysis_rate_limit_callback
        )
    },
    "keyword": {
        "user": UserRateLimiter(
            limiter=Limiter(Rate(analysis_rate_limit_settings.rate_limit_analysis_keyword, Duration.HOUR))
        ),
        "ip": FastAPILimiter(
            limiter=Limiter(Rate(analysis_rate_limit_settings.rate_limit_analysis_keyword, Duration.HOUR)),
            identifier=get_ip_identifier,
            callback=analysis_rate_limit_callback
        )
    },
    "resume": {
        "user": UserRateLimiter(
            limiter=Limiter(Rate(analysis_rate_limit_settings.rate_limit_export_resume, Duration.HOUR))
        ),
        "ip": FastAPILimiter(
            limiter=Limiter(Rate(analysis_rate_limit_settings.rate_limit_export_resume, Duration.HOUR)),
            identifier=get_ip_identifier,
            callback=analysis_rate_limit_callback
        )
    },
    "cover_letter": {
        "user": UserRateLimiter(
            limiter=Limiter(Rate(analysis_rate_limit_settings.rate_limit_export_cover_letter, Duration.HOUR))
        ),
        "ip": FastAPILimiter(
            limiter=Limiter(Rate(analysis_rate_limit_settings.rate_limit_export_cover_letter, Duration.HOUR)),
            identifier=get_ip_identifier,
            callback=analysis_rate_limit_callback
        )
    }
}
