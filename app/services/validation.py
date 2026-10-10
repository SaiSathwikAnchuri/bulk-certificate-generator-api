"""Recipient and job input validation services."""

from dataclasses import dataclass
from typing import Any
from pydantic import ValidationError
from app.schemas import RecipientIn


@dataclass
class ValidRow:
    """Represents a validated recipient row."""

    row_index: int
    name: str
    email: str
    raw_data: dict[str, Any]


@dataclass
class InvalidRow:
    """Represents an invalid recipient row with human-readable error."""

    row_index: int
    error: str
    raw_data: Any


def format_validation_error(err: ValidationError) -> str:
    """Convert Pydantic validation error into clean 'field: message' format."""
    messages = []
    for e in err.errors():
        field = ".".join(str(loc) for loc in e["loc"]) if e["loc"] else "row"
        msg = e["msg"]
        # Strip internal Pydantic prefixes
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, ") :]
        elif msg.startswith("String should have at least 1 character"):
            msg = "must not be blank"
        elif "value is not a valid email address" in msg:
            msg = "not a valid email address"
        messages.append(f"{field}: {msg}")
    return "; ".join(messages)


def validate_recipients(
    recipients_raw: list[Any],
) -> tuple[list[ValidRow], list[InvalidRow]]:
    """Validate a list of raw recipient rows at row-level.

    Returns:
        tuple of (valid_rows, invalid_rows)
    """
    valid_rows: list[ValidRow] = []
    invalid_rows: list[InvalidRow] = []
    seen_emails: dict[str, int] = {}

    for idx, row in enumerate(recipients_raw):
        # Row must be an object/dict
        if not isinstance(row, dict):
            invalid_rows.append(
                InvalidRow(
                    row_index=idx,
                    error="must be an object",
                    raw_data=row if isinstance(row, (str, int, float, bool)) else str(row),
                )
            )
            continue

        try:
            model = RecipientIn.model_validate(row)
        except ValidationError as err:
            invalid_rows.append(
                InvalidRow(
                    row_index=idx,
                    error=format_validation_error(err),
                    raw_data=row,
                )
            )
            continue

        # Check for duplicate email within the same request
        email_key = model.email
        if email_key in seen_emails:
            first_idx = seen_emails[email_key]
            invalid_rows.append(
                InvalidRow(
                    row_index=idx,
                    error=f"duplicate email (first seen at row {first_idx})",
                    raw_data=row,
                )
            )
            continue

        seen_emails[email_key] = idx
        valid_rows.append(
            ValidRow(
                row_index=idx,
                name=model.name,
                email=model.email,
                raw_data=row,
            )
        )

    return valid_rows, invalid_rows
