from os import getenv
import jwt
from pydantic import EmailStr
from pydantic.main import BaseModel
import requests

GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_CERTS_ENDPOINT = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_CLIENT_ID_KEY = "GOOGLE_CLIENT_ID"
GOOGLE_CLIENT_SECRET_KEY = "GOOGLE_CLIENT_SECRET"
GOOGLE_TOKEN_DECODE_ALGS = ["RS256"]

class GoogleOauthResponse(BaseModel):
    id: str
    email: EmailStr

class TokenResponseModel(BaseModel):
    id_token: str

def get_google_public_keys(id_token: str):
    jwk_client = jwt.PyJWKClient(GOOGLE_CERTS_ENDPOINT)
    return jwk_client.get_signing_key_from_jwt(id_token)

def google_login(code: str, redirect_uri: str):
    post_data = {
        "client_id": getenv(GOOGLE_CLIENT_ID_KEY),
        "client_secret": getenv(GOOGLE_CLIENT_SECRET_KEY),
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code"
    }
    r = requests.post(GOOGLE_TOKEN_ENDPOINT, data=post_data)
    if r.status_code != 200:
        return None
    
    token_data = TokenResponseModel(**r.json())  # pyright: ignore[reportAny]
    id_token: str = token_data.id_token

    try:
        payload = jwt.decode(
            id_token,
            get_google_public_keys(id_token),
            algorithms=GOOGLE_TOKEN_DECODE_ALGS,
            audience=getenv(GOOGLE_CLIENT_ID_KEY),
            issuer="https://accounts.google.com"
        )
    except jwt.exceptions.ExpiredSignatureError:
        return None
    except jwt.exceptions.InvalidSignatureError:
        return None

    return payload