from src.api.models.base import SuccessResponseWithData, LoginData, SuccessResponse

class LoginResponse(SuccessResponseWithData[LoginData]):
    pass

class SignupResponse(SuccessResponse):
    pass