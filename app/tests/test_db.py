from src.db.red import store_code, get_code, delete_code

def test_full_flow():
    email = "a@test.com"

    store_code(email, "123456")
    assert get_code(email) == "123456"

    store_code(email, "999999")
    assert get_code(email) == "999999"

    delete_code(email)
    assert get_code(email) is None