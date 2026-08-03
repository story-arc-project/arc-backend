from src.api.models.base import AuthMeData, BookmarkData, ComprehensiveAnalysisData, ComprehensiveAnalysisList, CoverLetterData, CoverLetterList, FileMetadataPublic, IndividualAnalysisData, IndividualAnalysisList, OnboardResponseData, PresignUploadData, PromptShownData, RefreshData, ResumeData, ResumeList, SuccessResponseWithData, LoginData, SuccessResponse, UUIDData, KeywordAnalysisList, KeywordAnalysisData, ErrorResponse

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

class PutSuccessResponse(SuccessResponse):
    pass

class DeleteSuccessResponse(SuccessResponse):
    pass

class IndividualAnalysisListResponse(SuccessResponseWithData[IndividualAnalysisList]):
    pass

class IndividualAnalysisResponse(SuccessResponseWithData[IndividualAnalysisData]):
    pass

class ComprehensiveAnalysisListResponse(SuccessResponseWithData[ComprehensiveAnalysisList]):
    pass

class ComprehensiveAnalysisResponse(SuccessResponseWithData[ComprehensiveAnalysisData]):
    pass

class KeywordAnalysisListResponse(SuccessResponseWithData[KeywordAnalysisList]):
    pass

class KeywordAnalysisResponse(SuccessResponseWithData[KeywordAnalysisData]):
    pass

class ResumeListResponse(SuccessResponseWithData[ResumeList]):
    pass

class ResumeResponse(SuccessResponseWithData[ResumeData]):
    pass

class OnboardConsentErrorResponse(ErrorResponse):
    missing_consent: list[str]

class PresignUploadResponse(SuccessResponseWithData):
    data: PresignUploadData

class FileListResponse(SuccessResponseWithData):
    data: list[FileMetadataPublic]

class FileMetadataResponse(SuccessResponseWithData):
    data: FileMetadataPublic

class FileDownloadResponse(SuccessResponseWithData):
    data: str

class BookmarkListResponse(SuccessResponseWithData):
    data: list[BookmarkData]

class CoverLetterListResponse(SuccessResponseWithData[CoverLetterList]):
    pass

class CoverLetterResponse(SuccessResponseWithData[CoverLetterData]):
    pass

class PromptShownResponse(SuccessResponseWithData):
    data: PromptShownData