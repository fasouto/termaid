"""CLI diagnostics, printed as text for people or as JSON lines for tools."""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from typing import Literal, Mapping


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    exit_code: int = 1
    severity: Literal["error", "warning"] = "error"
    details: Mapping[str, str | int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "details": dict(self.details),
            "exit_code": self.exit_code,
        }

    def emit(self, output_format: str = "text") -> int:
        """Write the diagnostic to stderr and return its exit code.

        Text messages that already open with the severity word (such as
        "Error rendering diagram: ...") are printed without a second prefix,
        so the text output reads as it always has.
        """
        if output_format == "json":
            line = json.dumps(self.to_dict(), ensure_ascii=False)
        else:
            prefix = self.severity.capitalize()
            line = self.message if self.message.startswith(prefix) else f"{prefix}: {self.message}"
        print(line, file=sys.stderr)
        return self.exit_code
