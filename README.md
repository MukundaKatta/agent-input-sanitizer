# agent-input-sanitizer

Sanitize user input before sending to an LLM.

Apply composable rules to clean text: strip control characters, normalize whitespace, collapse blank lines, cap length or line count, and add custom callables. Results wrap the cleaned text with a change log.

## Install

```bash
pip install agent-input-sanitizer
```

## Quick start

```python
from agent_input_sanitizer import InputSanitizer

sanitizer = InputSanitizer(max_length=500, max_lines=20)
result = sanitizer.sanitize(user_message)

print(result.sanitized)    # cleaned text
print(result.was_modified) # True if anything changed
print(result.changes)      # ['stripped 2 control char(s)', 'normalized whitespace']

# One-liner
clean = InputSanitizer.quick(user_message, max_length=500)
```

## API

### `InputSanitizer`

```python
InputSanitizer(
    *,
    strip_control_chars: bool = True,
    normalize_whitespace: bool = True,
    collapse_blank_lines: bool = True,
    max_length: int | None = None,
    max_lines: int | None = None,
)
```

| Method | Description |
|---|---|
| `sanitize(text)` | Apply all rules; returns `SanitizeResult` |
| `add_rule(fn, *, description)` | Add custom `(str) -> str` rule; chainable |
| `InputSanitizer.quick(text, *, max_length, max_lines)` | Sanitize and return the string directly |

**Built-in rules** (applied in order):
1. Strip ASCII control chars (keeps `\t`, `\n`, `\r`)
2. Collapse runs of spaces/tabs; strip trailing whitespace per line
3. Reduce 3+ consecutive blank lines to 2
4. Truncate to `max_lines` lines
5. Truncate to `max_length` characters
6. Custom rules (in registration order)

### `SanitizeResult`

| Attribute | Type | Description |
|---|---|---|
| `original` | `str` | Input before sanitization |
| `sanitized` | `str` | Text after all rules |
| `changes` | `list[str]` | Human-readable change log |
| `was_modified` | `bool` | `True` if sanitized != original |
| `to_dict()` | `dict` | JSON-serialisable representation |

## License

MIT
