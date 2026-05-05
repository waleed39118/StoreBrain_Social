"""
core/exceptions.py
تسلسل هرمي لاستثناءات StoreBrain Social
"""


class StoreBrainError(Exception):
    def __init__(self, message: str, code: str = "SB_ERR") -> None:
        super().__init__(message)
        self.message = message
        self.code    = code

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class ConfigError(StoreBrainError):
    def __init__(self, message: str) -> None:
        super().__init__(message, "CFG_ERR")


class MissingKeyError(ConfigError):
    def __init__(self, key: str) -> None:
        super().__init__(f"المفتاح '{key}' مفقود في ملف .env")
        self.key_name = key


class ShopifyError(StoreBrainError):
    def __init__(self, message: str, status_code: int = 0) -> None:
        super().__init__(message, "SHOP_ERR")
        self.status_code = status_code


class AIError(StoreBrainError):
    def __init__(self, message: str) -> None:
        super().__init__(message, "AI_ERR")


class PublishError(StoreBrainError):
    def __init__(self, platform: str, message: str, status_code: int = 0) -> None:
        super().__init__(f"[{platform}] {message}", "PUB_ERR")
        self.platform    = platform
        self.status_code = status_code


class AuthError(PublishError):
    def __init__(self, platform: str) -> None:
        super().__init__(platform, "مفتاح API غير صالح أو منتهي الصلاحية.", 401)


class RateLimitError(PublishError):
    def __init__(self, platform: str) -> None:
        super().__init__(platform, "تجاوزت حد الطلبات — انتظر قليلاً.", 429)
