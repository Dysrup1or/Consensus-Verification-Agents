"""
Core Judges - Built-in judge plugins for CVA.
"""

from .architect import ArchitectJudge
from .security import SecurityJudge
from .user_proxy import UserProxyJudge

__all__ = [
    "ArchitectJudge",
    "SecurityJudge",
    "UserProxyJudge",
]
