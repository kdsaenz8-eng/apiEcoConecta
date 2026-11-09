import hashlib
import hmac
import unittest

SECRET_SALT = b"ecoconecta_ecoconecta_secure_salt_2026"

def verify_password_adapter(plain_password: str, hashed_password: str) -> bool:
    if not plain_password or not hashed_password:
        return False

    # 1. PBKDF2 64 hex characters (Base de datos municipal)
    if len(hashed_password) == 64 and not hashed_password.startswith("$"):
        try:
            expected = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), SECRET_SALT, 100000).hex()
            if hmac.compare_digest(expected, hashed_password):
                return True
        except Exception:
            pass

    # 2. Manejo controlado para evitar HTTP 500
    return False

class TestPasswordDualHashing(unittest.TestCase):
    def test_verify_pbkdf2_municipal_hash(self):
        password = "EcoPassword2026"
        municipal_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), SECRET_SALT, 100000).hex()
        self.assertEqual(len(municipal_hash), 64)
        self.assertTrue(verify_password_adapter(password, municipal_hash))

    def test_verify_pbkdf2_incorrect_password(self):
        password = "WrongPassword"
        municipal_hash = hashlib.pbkdf2_hmac("sha256", "EcoPassword2026".encode("utf-8"), SECRET_SALT, 100000).hex()
        self.assertFalse(verify_password_adapter(password, municipal_hash))

    def test_invalid_hash_does_not_raise_exception(self):
        self.assertFalse(verify_password_adapter("EcoPassword2026", "corrupted_hash"))
        self.assertFalse(verify_password_adapter("", ""))

if __name__ == "__main__":
    unittest.main()

