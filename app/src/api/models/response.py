from src.api.models.base import SuccessResponseWithData, LoginData, SuccessResponse

class LoginResponse(SuccessResponseWithData[LoginData]):
    pass

class SignupResponse(SuccessResponse):
    pass

class VerificationSentResponse(SuccessResponse):
    message: str = "If an account exists with that email, a new verification code has been sent."