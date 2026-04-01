import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from os import getenv

from pydantic import EmailStr

def get_password():
    p = getenv("GMAIL_PASSWORD")
    if p is None:
        raise ValueError("Gmail app password is not set.")
    return p

def send_mail(to: EmailStr, subject: str, body: str):
    email = getenv("GMAIL")
    if email is None:
        raise ValueError("Gmail address is not set.")

    msg = MIMEMultipart()
    msg["From"] = email
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        _ = server.starttls()
        _ = server.login(email, get_password())
        errors = server.send_message(msg)
        if errors:
            return errors