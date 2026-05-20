import httpx

client = httpx.Client()

# res = client.post("http://localhost:8000/auth/signup", json={
#     "email": "bunniesnu@gmail.com",
#     "password": "testpassword"
# })
# print(res.status_code, res.text)

# code = input()

# res = client.post("http://localhost:8000/auth/verify-email", json={
#     "email": "bunniesnu@gmail.com",
#     "code": code
# })
# print(res.status_code)

res = client.post("http://localhost:8000/experiences/comprehensive", json={
    
})