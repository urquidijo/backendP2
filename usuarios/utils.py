from django.core import signing

AUTH_TOKEN_SALT = "usuarios.auth"
TOKEN_MAX_AGE_SECONDS = 60 * 60 * 24 * 7  # 7 days


def create_auth_token(user_id: int) -> str:
    """
    Returns a signed token that encodes the user id.
    """
    return signing.dumps({"user_id": user_id}, salt=AUTH_TOKEN_SALT)


def verify_auth_token(token: str) -> int | None:
    """
    Validates the token and returns the user id, or None if invalid/expired.
    """
    try:
        data = signing.loads(token, salt=AUTH_TOKEN_SALT, max_age=TOKEN_MAX_AGE_SECONDS)
    except signing.BadSignature:
        return None

    return data.get("user_id")
