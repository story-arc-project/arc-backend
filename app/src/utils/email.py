import hashlib
import re
from typing import Any

from pydantic import GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema


_HEX_SHA256_REGEX = re.compile(r"^[a-f0-9]{64}$")


def hash_email(email: str) -> "HashEmail":
    """Return SHA-256(trim(lowercase(email)))."""
    normalized = email.strip().lower().encode("utf-8")
    digest = hashlib.sha256(normalized).hexdigest()
    return HashEmail(digest)

class _HashEmailPydanticAnnotation:
    @classmethod
    def __get_pydantic_core_schema__(
        cls, _source_type: Any, _handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        def validate(value: Any) -> "HashEmail":
            if not isinstance(value, str):
                raise TypeError("HashEmail must be a string")
            # Allow empty string if used as placeholder before before_insert hooks
            if value == "" or _HEX_SHA256_REGEX.fullmatch(value):
                return HashEmail(value)
            raise ValueError("HashEmail must be a 64-character lowercase hexadecimal SHA-256 digest")

        return core_schema.chain_schema(
            [
                core_schema.str_schema(max_length=64),
                core_schema.no_info_plain_validator_function(validate),
            ]
        )

class HashEmail(str):
    """64-character hex string representing SHA-256 hashed email."""

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        return _HashEmailPydanticAnnotation.__get_pydantic_core_schema__(
            source_type, handler
        )
