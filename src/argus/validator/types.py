"""Type definitions for the validator module."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ValidationResult:
    """Result of a message validation."""

    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    validated_at: datetime = field(default_factory=lambda: datetime.now())

    # Details about specific validation checks
    sections_valid: bool = True
    bullet_counts_valid: bool = True
    no_hallucinations: bool = True
    formatting_valid: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "validated_at": self.validated_at.isoformat(),
            "sections_valid": self.sections_valid,
            "bullet_counts_valid": self.bullet_counts_valid,
            "no_hallucinations": self.no_hallucinations,
            "formatting_valid": self.formatting_valid,
        }
