from src.api.models.base import ErrorResponse


class AppException(Exception):
    def __init__(self, status_code: int, error: ErrorResponse):
        super().__init__()
        self.status_code: int = status_code
        self.error: ErrorResponse = error