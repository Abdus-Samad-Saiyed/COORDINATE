"""
Alpha / Staging settings for Campus Nexus.
Used for on-campus pilot and staging validation.
Inherits all strict production security invariants (PostgreSQL, Redis, secret key length,
strict hosts), with DEBUG = False and ALPHA_MODE = True.
"""
from .prod import *  # noqa: F401, F403

ALPHA_MODE = True
