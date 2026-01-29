from enum import Enum


class OAuthProviders(str, Enum):
    GOOGLE = "google"
    GITHUB = "github"
