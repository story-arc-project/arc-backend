from src.api.models.base import OnboardResponseData, RefreshData, SuccessResponseWithData, LoginData, SuccessResponse

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