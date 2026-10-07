from datetime import date

def render_verification_mail_html(code: str, expire_minutes: int, support_email: str) -> str:
    current_year = date.today().year
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ARC 이메일 인증</title>
</head>
<body style="margin:0; padding:0; background-color:#f4f5f7; font-family:'Apple SD Gothic Neo', 'Malgun Gothic', -apple-system, BlinkMacSystemFont, sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f5f7; padding:32px 16px;">
  <tr>
    <td align="center">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:480px; background-color:#ffffff; border-radius:12px; overflow:hidden; border:1px solid #e5e7eb;">

        <tr>
          <td style="padding:32px 32px 0 32px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td>
                  <span style="font-size:20px; font-weight:700; color:#111827; letter-spacing:-0.02em;">ARC</span>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <tr>
          <td style="padding:24px 32px 0 32px;">
            <p style="margin:0; font-size:16px; line-height:1.6; color:#111827; font-weight:600;">
              이메일 인증번호를 안내드립니다
            </p>
            <p style="margin:8px 0 0 0; font-size:14px; line-height:1.6; color:#6b7280;">
              아래 인증번호를 인증 화면에 입력해 주세요.
            </p>
          </td>
        </tr>

        <tr>
          <td style="padding:24px 32px 0 32px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f9fafb; border-radius:8px; border:1px solid #e5e7eb;">
              <tr>
                <td align="center" style="padding:24px 16px;">
                  <span style="font-size:32px; font-weight:700; letter-spacing:0.3em; color:#111827; font-family:'SF Mono', 'Courier New', monospace;">
                    {code}
                  </span>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <tr>
          <td style="padding:16px 32px 0 32px;">
            <p style="margin:0; font-size:13px; line-height:1.6; color:#9ca3af; text-align:center;">
              이 인증번호는 <strong style="color:#6b7280;">{expire_minutes}분</strong> 동안 유효합니다.
            </p>
          </td>
        </tr>

        <tr>
          <td style="padding:24px 32px 0 32px;">
            <hr style="border:none; border-top:1px solid #e5e7eb; margin:0;">
          </td>
        </tr>

        <tr>
          <td style="padding:20px 32px 0 32px;">
            <p style="margin:0; font-size:13px; line-height:1.7; color:#9ca3af;">
              본인이 요청하지 않은 인증이라면 이 메일을 무시해 주세요. 계정에는 어떠한 변경도 발생하지 않습니다.
            </p>
          </td>
        </tr>

        <tr>
          <td style="padding:24px 32px 32px 32px;">
            <p style="margin:0; font-size:12px; line-height:1.6; color:#c1c5cc;">
              본 메일은 발신 전용입니다. 문의사항은 <a href="mailto:{support_email}" style="color:#9ca3af; text-decoration:underline;">{support_email}</a>로 연락해 주세요.
            </p>
            <p style="margin:8px 0 0 0; font-size:12px; color:#c1c5cc;">
              © {current_year} ARC. All rights reserved.
            </p>
          </td>
        </tr>

      </table>
    </td>
  </tr>
</table>
</body>
</html>"""

def render_verification_mail_text(code: str, expire_minutes: int, support_email: str) -> str:
    current_year = date.today().year
    return f"""[ARC] 이메일 인증번호 안내

아래 인증번호를 인증 화면에 입력해 주세요.

인증번호: {code}

이 인증번호는 {expire_minutes}분 동안 유효합니다.

본인이 요청하지 않은 인증이라면 이 메일을 무시해 주세요.
계정에는 어떠한 변경도 발생하지 않습니다.

---
본 메일은 발신 전용입니다. 문의사항은 {support_email}로 연락해 주세요.
© {current_year} ARC. All rights reserved."""