import random

from pydantic import EmailStr

from src.utils.mail import send_mail
from src.db.red import delete_code, get_code, store_code

def __generate_code():
    return str(random.randint(100000, 999999))

def _generate_code(email: EmailStr):
    code = __generate_code()
    store_code(email, code)
    return code

def verify_code(email: str, user_code: str):
    stored_code = get_code(email)

    if not stored_code or stored_code != user_code:
        return False
    
    delete_code(email)
    return True

def send_code(email: EmailStr):
    code = _generate_code(email)
    return send_mail(
        email,
        "ARC verification code",
        code
    )