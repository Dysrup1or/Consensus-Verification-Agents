"""
Domain-Specific Judges - Compliance and regulatory plugins.
"""

from .hipaa import HIPAAJudge
from .pci_dss import PCIDSSJudge

__all__ = [
    "HIPAAJudge",
    "PCIDSSJudge",
]
