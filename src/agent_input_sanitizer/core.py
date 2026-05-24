"""Sanitize user input before sending to an LLM.

:class:`InputSanitizer` applies a composable set of rules to text: strip
null/control characters, normalize whitespace, cap length, limit lines, and
run custom callables.  Results are wrapped in :class:`SanitizeResult` so
callers can inspect exactly what changed.

Example::

    from agent_input_sanitizer import InputSanitizer

    sanitizer = InputSanitizer(max_length=500, strip_control_chars=True)
    result = sanitizer.sanitize("Hello\\x00 World!\\n\\n\\n  Extra spaces   ")

    print(result.sanitized)    # 'Hello World!\\n\\nExtra spaces'
    print(result.was_modified) # True
    print(result.changes)      # ['stripped 1 control char(s)', ...]
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SanitizeResult:
    """Result of a sanitize pass.

    Attributes:
        original:     The input text before sanitization.
        sanitized:    The text after all rules have been applied.
        changes:      Human-readable descriptions of each modification made.
        was_modified: ``True`` if *sanitized* differs from *original*.
    """

    original: str
    sanitized: str
    changes: list[str] = field(default_factory=list)

    @property
    def was_modified(self) -> bool:
        """``True`` if the sanitized text differs from the original."""
        return self.sanitized != self.original

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict."""
        return {
            "original": self.original,
            "sanitized": self.sanitized,
            "changes": list(self.changes),
            "was_modified": self.was_modified,
        }

    def __repr__(self) -> str:
        return (
            f"SanitizeResult(was_modified={self.was_modified},"
            f" changes={len(self.changes)})"
        )


class InputSanitizer:
    """Sanitize text with configurable built-in rules and custom callables.

    Built-in rules (all enabled by default unless overridden):

    * **strip_control_chars** — remove ASCII control characters (\\x00–\\x1f,
      \\x7f) except ``\\t``, ``\\n``, ``\\r``.
    * **normalize_whitespace** — collapse runs of spaces/tabs into a single
      space and remove trailing whitespace from each line.
    * **collapse_blank_lines** — reduce runs of two or more blank lines down
      to one blank line.
    * **max_length** — truncate to at most *max_length* characters.
    * **max_lines** — truncate to at most *max_lines* lines.

    Custom rules are callables ``(str) -> str`` appended via :meth:`add_rule`.

    Example::

        sanitizer = InputSanitizer(max_length=1000, max_lines=20)
        sanitizer.add_rule(lambda s: s.strip(), description="strip edges")
        result = sanitizer.sanitize(user_message)
    """

    def __init__(
        self,
        *,
        strip_control_chars: bool = True,
        normalize_whitespace: bool = True,
        collapse_blank_lines: bool = True,
        max_length: int | None = None,
        max_lines: int | None = None,
    ) -> None:
        self._strip_control_chars = strip_control_chars
        self._normalize_whitespace = normalize_whitespace
        self._collapse_blank_lines = collapse_blank_lines
        self._max_length = max_length
        self._max_lines = max_lines
        self._custom_rules: list[tuple[Callable[[str], str], str]] = []

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def add_rule(
        self,
        fn: Callable[[str], str],
        *,
        description: str = "custom rule",
    ) -> InputSanitizer:
        """Add a custom sanitization rule.

        Args:
            fn:          Callable that takes and returns a string.
            description: Label used in :attr:`SanitizeResult.changes`.

        Returns:
            ``self`` for chaining.
        """
        self._custom_rules.append((fn, description))
        return self

    # ------------------------------------------------------------------
    # Sanitization
    # ------------------------------------------------------------------

    def sanitize(self, text: str) -> SanitizeResult:
        """Apply all configured rules to *text*.

        Args:
            text: The raw input string.

        Returns:
            A :class:`SanitizeResult` with the cleaned text and a change log.
        """
        changes: list[str] = []
        current = text

        # 1. Strip control characters
        if self._strip_control_chars:
            cleaned, n = _strip_control_characters(current)
            if n > 0:
                changes.append(f"stripped {n} control char(s)")
                current = cleaned

        # 2. Normalize whitespace (per line)
        if self._normalize_whitespace:
            cleaned = _normalize_whitespace(current)
            if cleaned != current:
                changes.append("normalized whitespace")
                current = cleaned

        # 3. Collapse blank lines
        if self._collapse_blank_lines:
            cleaned = _collapse_blank_lines(current)
            if cleaned != current:
                changes.append("collapsed blank lines")
                current = cleaned

        # 4. Limit lines
        if self._max_lines is not None:
            cleaned = _limit_lines(current, self._max_lines)
            if cleaned != current:
                lines_in = len(current.splitlines())
                changes.append(f"truncated to {self._max_lines} lines (was {lines_in})")
                current = cleaned

        # 5. Limit length
        if self._max_length is not None and len(current) > self._max_length:
            old_len = len(current)
            current = current[: self._max_length]
            changes.append(f"truncated to {self._max_length} chars (was {old_len})")

        # 6. Custom rules
        for fn, desc in self._custom_rules:
            result = fn(current)
            if result != current:
                changes.append(desc)
                current = result

        return SanitizeResult(original=text, sanitized=current, changes=changes)

    @classmethod
    def quick(
        cls,
        text: str,
        *,
        max_length: int | None = None,
        max_lines: int | None = None,
    ) -> str:
        """Convenience class method — sanitize and return the cleaned string.

        Uses all default rules plus optional *max_length* / *max_lines*.
        """
        sanitizer = cls(max_length=max_length, max_lines=max_lines)
        return sanitizer.sanitize(text).sanitized

    def __repr__(self) -> str:
        parts = []
        if self._max_length is not None:
            parts.append(f"max_length={self._max_length}")
        if self._max_lines is not None:
            parts.append(f"max_lines={self._max_lines}")
        parts.append(f"custom_rules={len(self._custom_rules)}")
        return f"InputSanitizer({', '.join(parts)})"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Control chars to remove: 0x00–0x08, 0x0B–0x0C, 0x0E–0x1F, 0x7F
# Keep: 0x09 (tab), 0x0A (LF), 0x0D (CR)
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _strip_control_characters(text: str) -> tuple[str, int]:
    """Remove ASCII control characters, preserving tab/LF/CR.

    Returns ``(cleaned_text, count_removed)``.
    """
    matches = _CONTROL_CHAR_RE.findall(text)
    if not matches:
        return text, 0
    cleaned = _CONTROL_CHAR_RE.sub("", text)
    return cleaned, len(matches)


def _normalize_whitespace(text: str) -> str:
    """Collapse multiple spaces/tabs into one and strip trailing whitespace."""
    lines = text.split("\n")
    normalized = []
    for line in lines:
        # Collapse runs of spaces/tabs (not newlines)
        line = re.sub(r"[ \t]+", " ", line)
        # Strip trailing whitespace
        line = line.rstrip()
        normalized.append(line)
    return "\n".join(normalized)


def _collapse_blank_lines(text: str) -> str:
    """Reduce three or more consecutive newlines down to two."""
    return re.sub(r"\n{3,}", "\n\n", text)


def _limit_lines(text: str, max_lines: int) -> str:
    """Keep only the first *max_lines* lines."""
    lines = text.split("\n")
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:max_lines])


def _is_control_char(c: str) -> bool:
    """Return ``True`` if *c* is an ASCII control character (non-printable)."""
    cat = unicodedata.category(c)
    return cat == "Cc" and c not in {"\t", "\n", "\r"}
