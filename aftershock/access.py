"""Optional operator gate for a publicly reachable demonstration."""

import base64
import binascii
import hmac
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class OperatorAccess:
    username: str
    password: str
    secure_cookies: bool

    @classmethod
    def from_environment(cls):
        required = os.environ.get("AFTERSHOCK_REQUIRE_AUTH", "false").lower() == "true"
        password = os.environ.get("AFTERSHOCK_OPERATOR_PASSWORD", "")
        username = os.environ.get("AFTERSHOCK_OPERATOR_USER", "operator")
        if required and not password:
            raise ValueError("Public access requires AFTERSHOCK_OPERATOR_PASSWORD")
        if password and (len(password) < 16 or not username or ":" in username):
            raise ValueError(
                "Use an operator username and a password of at least 16 characters"
            )
        secure = os.environ.get("AFTERSHOCK_SECURE_COOKIE", "false").lower() == "true"
        return cls(username, password, secure)

    def accepts(self, authorization):
        if not self.password:
            return True
        try:
            scheme, encoded = (authorization or "").split(" ", 1)
            if scheme.lower() != "basic" or len(encoded) > 4096:
                return False
            username, password = (
                base64.b64decode(encoded, validate=True).decode("utf-8").split(":", 1)
            )
        except (ValueError, UnicodeDecodeError, binascii.Error):
            return False
        user_ok = hmac.compare_digest(username.encode(), self.username.encode())
        password_ok = hmac.compare_digest(password.encode(), self.password.encode())
        return user_ok & password_ok
