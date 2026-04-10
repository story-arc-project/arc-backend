from src.api.models.base import AuthMeData, OnboardResponseData, RefreshData, SuccessResponseWithData, LoginData, SuccessResponse, UUIDData

class LoginResponse(SuccessResponseWithData[LoginData]):
    pass

class SignupResponse(SuccessResponse):
    pass

class VerificationSentResponse(SuccessResponse):
    message: str = "If an account exists with that email, a new verification code has been sent."

class RefreshResponse(SuccessResponseWithData[RefreshData]):
    message: str = "Tokens refreshed successfully."

class OnboardResponse(SuccessResponseWithData[OnboardResponseData]):
    pass

class LogoutResponse(SuccessResponse):
    message: str = "Logout success"

class AuthMeResponse(SuccessResponseWithData[AuthMeData]):
    message: str = "User data fetch success"

class PostSuccessResponse(SuccessResponseWithData[UUIDData]):
    pass