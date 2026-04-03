from os import getenv

from src.const import ENVIRONMENT_KEY
from src.enums import Environment

def get_env():
    if getenv(ENVIRONMENT_KEY, Environment.PRODUCTION) == Environment.DEVELOPMENT:
        return Environment.DEVELOPMENT
    return Environment.PRODUCTION