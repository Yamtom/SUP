import base64
import hmac
import os
from hashlib import pbkdf2_hmac
ITERATIONS = 390000
ALGORITHM = "sha256"
KEY_LENGTH = 32


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    derived = pbkdf2_hmac(ALGORITHM, password.encode(), salt, ITERATIONS, dklen=KEY_LENGTH)
    return "{}${}${}".format(
        ITERATIONS,
        base64.b64encode(salt).decode(),
        base64.b64encode(derived).decode(),
    )


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        iterations_str, salt_b64, hash_b64 = stored_hash.split("$")
        iterations = int(iterations_str)
    except ValueError:
        return False

    salt = base64.b64decode(salt_b64)
    expected = base64.b64decode(hash_b64)
    derived = pbkdf2_hmac(ALGORITHM, password.encode(), salt, iterations, dklen=len(expected))
    return hmac.compare_digest(expected, derived)


def generate_token() -> str:
    return base64.urlsafe_b64encode(os.urandom(30)).decode().rstrip("=")
