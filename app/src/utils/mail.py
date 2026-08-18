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

def send_mail(to: EmailStr, subject: str, text_body: str, html_body: str):
    email = getenv("GMAIL")
    if email is None:
        raise ValueError("Gmail address is not set.")

    msg = MIMEMultipart("alternative")
    msg["From"] = f"ARC <{email}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP("smtp.mailgun.org", 587) as server:
        _ = server.starttls()
        _ = server.login(email, get_password())
        errors = server.send_message(msg)
        if errors:
            return errors