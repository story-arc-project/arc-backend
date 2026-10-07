from fastapi import Request

def get_ip(request: Request):
    x_forwarded_for = request.headers.get("x-forwarded-for")
    if x_forwarded_for:
        client_ip = x_forwarded_for.split(",")[0].strip()
    else:
        client = request.client
        if client is None:
            return None
        client_ip = client.host
    return client_ip

def get_user_agent(request: Request):
    user_agent = request.headers.get("user-agent")
    return user_agent