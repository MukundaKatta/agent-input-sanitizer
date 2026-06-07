"""Tests for agent-input-sanitizer."""

from __future__ import annotations

from agent_input_sanitizer import InputSanitizer, SanitizeResult

# ---------------------------------------------------------------------------
# SanitizeResult
# ---------------------------------------------------------------------------


def test_result_not_modified():
    result = SanitizeResult(original="hello", sanitized="hello")
    assert not result.was_modified
    assert result.changes == []


def test_result_modified():
    result = SanitizeResult(
        original="a\x00b",
        sanitized="ab",
        changes=["stripped 1 control char(s)"],
    )
    assert result.was_modified


def test_result_to_dict():
    result = SanitizeResult(original="hi", sanitized="hi")
    d = result.to_dict()
    assert d["original"] == "hi"
    assert d["sanitized"] == "hi"
    assert d["was_modified"] is False
    assert d["changes"] == []


def test_result_repr():
    result = SanitizeResult(original="a", sanitized="b", changes=["x"])
    r = repr(result)
    assert "SanitizeResult" in r
    assert "was_modified=True" in r


# ---------------------------------------------------------------------------
# Strip control characters
# ---------------------------------------------------------------------------


def test_strip_null_char():
    s = InputSanitizer()
    result = s.sanitize("hello\x00world")
    assert result.sanitized == "helloworld"
    assert result.was_modified


def test_strip_multiple_control_chars():
    s = InputSanitizer()
    result = s.sanitize("\x01\x02\x03abc")
    assert result.sanitized == "abc"
    assert any("3" in c for c in result.changes)


def test_tab_collapsed_to_space():
    # normalize_whitespace collapses tabs into spaces
    s = InputSanitizer()
    result = s.sanitize("col1\tcol2")
    assert result.sanitized == "col1 col2"


def test_preserves_newline():
    s = InputSanitizer()
    result = s.sanitize("line1\nline2")
    assert "\n" in result.sanitized


def test_crlf_normalized():
    # normalize_whitespace strips trailing \r from each line
    s = InputSanitizer()
    result = s.sanitize("line1\r\nline2")
    assert "line1" in result.sanitized
    assert "line2" in result.sanitized


def test_strips_del_char():
    s = InputSanitizer()
    result = s.sanitize("abc\x7fdef")
    assert result.sanitized == "abcdef"


def test_no_control_chars_no_change():
    s = InputSanitizer()
    result = s.sanitize("clean text")
    assert not result.was_modified


def test_strip_control_disabled():
    s = InputSanitizer(strip_control_chars=False)
    result = s.sanitize("abc\x00def")
    assert "\x00" in result.sanitized


# ---------------------------------------------------------------------------
# Normalize whitespace
# ---------------------------------------------------------------------------


def test_collapse_spaces():
    s = InputSanitizer()
    result = s.sanitize("hello    world")
    assert result.sanitized == "hello world"


def test_collapse_tabs_to_space():
    # multiple tabs collapse to a single space
    s = InputSanitizer()
    result = s.sanitize("a\t\t\tb")
    assert result.sanitized == "a b"


def test_strip_trailing_whitespace():
    s = InputSanitizer()
    result = s.sanitize("hello   \nworld  ")
    lines = result.sanitized.split("\n")
    assert lines[0] == "hello"
    assert lines[1] == "world"


def test_leading_whitespace_collapsed_not_stripped():
    # Leading whitespace on a line is collapsed to a single space, not removed.
    s = InputSanitizer()
    result = s.sanitize("a\n   leading")
    assert result.sanitized == "a\n leading"


def test_normalize_disabled():
    s = InputSanitizer(normalize_whitespace=False)
    result = s.sanitize("a   b")
    assert "   " in result.sanitized


def test_normalize_no_change():
    s = InputSanitizer()
    result = s.sanitize("already clean")
    # normalize still runs but produces no change log entry
    assert "normalized whitespace" not in result.changes


# ---------------------------------------------------------------------------
# Collapse blank lines
# ---------------------------------------------------------------------------


def test_collapse_triple_blank_lines():
    s = InputSanitizer()
    result = s.sanitize("a\n\n\n\nb")
    assert result.sanitized == "a\n\nb"


def test_collapse_many_blank_lines():
    s = InputSanitizer()
    result = s.sanitize("x\n\n\n\n\n\ny")
    assert result.sanitized == "x\n\ny"


def test_two_blank_lines_unchanged():
    s = InputSanitizer()
    text = "a\n\nb"
    result = s.sanitize(text)
    assert result.sanitized == text


def test_collapse_blank_disabled():
    s = InputSanitizer(collapse_blank_lines=False)
    text = "a\n\n\n\nb"
    result = s.sanitize(text)
    assert result.sanitized == text


# ---------------------------------------------------------------------------
# max_length
# ---------------------------------------------------------------------------


def test_max_length_truncates():
    s = InputSanitizer(max_length=5)
    result = s.sanitize("hello world")
    assert result.sanitized == "hello"
    assert result.was_modified


def test_max_length_exact_fit():
    s = InputSanitizer(max_length=5)
    result = s.sanitize("hello")
    assert result.sanitized == "hello"
    assert not result.was_modified


def test_max_length_change_recorded():
    s = InputSanitizer(max_length=3)
    result = s.sanitize("abcde")
    assert any("3" in c for c in result.changes)


def test_max_length_none_no_truncation():
    s = InputSanitizer(max_length=None)
    long_text = "a" * 10_000
    result = s.sanitize(long_text)
    assert len(result.sanitized) == 10_000


# ---------------------------------------------------------------------------
# max_lines
# ---------------------------------------------------------------------------


def test_max_lines_truncates():
    s = InputSanitizer(max_lines=2)
    result = s.sanitize("a\nb\nc\nd")
    assert result.sanitized == "a\nb"


def test_max_lines_exact():
    s = InputSanitizer(max_lines=3)
    result = s.sanitize("a\nb\nc")
    assert result.sanitized == "a\nb\nc"
    assert not result.was_modified


def test_max_lines_change_recorded():
    s = InputSanitizer(max_lines=1)
    result = s.sanitize("line1\nline2\nline3")
    assert any("1" in c for c in result.changes)


def test_max_lines_single_line():
    s = InputSanitizer(max_lines=1)
    result = s.sanitize("only one line")
    assert result.sanitized == "only one line"


# ---------------------------------------------------------------------------
# Custom rules
# ---------------------------------------------------------------------------


def test_add_rule_applied():
    s = InputSanitizer()
    s.add_rule(str.upper, description="uppercased")
    result = s.sanitize("hello")
    assert result.sanitized == "HELLO"
    assert "uppercased" in result.changes


def test_add_rule_chaining():
    s = InputSanitizer()
    result = (
        s.add_rule(lambda t: t.replace("foo", "bar"), description="replaced foo")
        .add_rule(lambda t: t.strip(), description="stripped")
        .sanitize("  foo  ")
    )
    assert result.sanitized == "bar"


def test_add_rule_no_change_not_logged():
    s = InputSanitizer()
    s.add_rule(lambda t: t, description="identity")
    result = s.sanitize("hello")
    assert "identity" not in result.changes


def test_multiple_custom_rules_order():
    s = InputSanitizer()
    s.add_rule(lambda t: t + "1", description="append 1")
    s.add_rule(lambda t: t + "2", description="append 2")
    result = s.sanitize("x")
    assert result.sanitized == "x12"


# ---------------------------------------------------------------------------
# quick()
# ---------------------------------------------------------------------------


def test_quick_returns_string():
    out = InputSanitizer.quick("hello\x00world")
    assert isinstance(out, str)
    assert "\x00" not in out


def test_quick_max_length():
    out = InputSanitizer.quick("hello world", max_length=5)
    assert out == "hello"


def test_quick_max_lines():
    out = InputSanitizer.quick("a\nb\nc", max_lines=2)
    assert out == "a\nb"


# ---------------------------------------------------------------------------
# repr
# ---------------------------------------------------------------------------


def test_repr_no_limits():
    s = InputSanitizer()
    r = repr(s)
    assert "InputSanitizer" in r


def test_repr_with_limits():
    s = InputSanitizer(max_length=100, max_lines=50)
    r = repr(s)
    assert "100" in r
    assert "50" in r


# ---------------------------------------------------------------------------
# Combined rules
# ---------------------------------------------------------------------------


def test_combined_rules():
    s = InputSanitizer(max_length=20, strip_control_chars=True)
    text = "hello\x00 world  extra text that goes on"
    result = s.sanitize(text)
    assert len(result.sanitized) <= 20
    assert "\x00" not in result.sanitized
    assert len(result.changes) >= 2


def test_module_docstring_example():
    # Mirrors the example in the module docstring / README.
    s = InputSanitizer(max_length=500, strip_control_chars=True)
    result = s.sanitize("Hello\x00 World!\n\n\n  Extra spaces   ")
    assert result.sanitized == "Hello World!\n\n Extra spaces"
    assert result.was_modified
    assert result.changes[0] == "stripped 1 control char(s)"
