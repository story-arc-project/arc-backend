from email.mime.multipart import MIMEMultipart
from unittest.mock import MagicMock

def get_sent_mail(mock_mail: MagicMock):
    sent_mail: MIMEMultipart = mock_mail.send_message.call_args.args[0]
    for part in sent_mail.walk():
        if part.is_multipart():
            continue

        if part.get_content_type() in ("text/plain", "text/html"):
            return {
                "To": sent_mail["To"],
                "Subject": sent_mail["Subject"],
                "Content-Type": part.get_content_type(),
                "Body": part.get_payload(decode=True).decode(
                    part.get_content_charset() or "utf-8"
                )
            }
    return {
        "To": sent_mail["To"],
        "Subject": sent_mail["Subject"],
        "Content-Type": None,
        "Body": None
    }