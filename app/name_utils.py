import re


KNOWN_TITLES = {"dr": "Dr", "ms": "Ms", "mr": "Mr", "mrs": "Mrs", "prof": "Prof"}


def normalize_title(title: str | None) -> str | None:
    if not title:
        return None
    cleaned = title.strip().rstrip(".").lower()
    return KNOWN_TITLES.get(cleaned, title.strip().rstrip("."))


def format_title(title: str | None) -> str:
    normalized = normalize_title(title)
    return f"{normalized}." if normalized in KNOWN_TITLES.values() else (normalized or "")


def split_title_from_name(full_name: str | None, title: str | None = None) -> tuple[str, str | None]:
    name = (full_name or "").strip()
    normalized_title = normalize_title(title)
    match = re.match(r"^(Dr|Ms|Mr|Mrs|Prof)\.?\s+(.+)$", name, flags=re.IGNORECASE)
    if match:
        normalized_title = normalized_title or normalize_title(match.group(1))
        name = match.group(2).lstrip(". ").strip()
    else:
        name = name.lstrip(". ").strip()
    return name, normalized_title
