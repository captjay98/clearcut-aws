from urllib.parse import urlsplit, urlunsplit

from clearcut.research.domain.snapshots import SearchResultItem


def canonicalize_https_url(value: str) -> str | None:
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
    except ValueError:
        return None

    if parsed.scheme.lower() != "https" or parsed.hostname is None:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None

    host = parsed.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    netloc = host if port in (None, 443) else f"{host}:{port}"
    return urlunsplit(("https", netloc, parsed.path, parsed.query, ""))


def select_extract_targets(
    search_results: list[SearchResultItem],
    max_targets: int = 3,
) -> list[str]:
    seen: set[str] = set()
    selected: list[str] = []

    for item in search_results:
        url = canonicalize_https_url(item.url)
        if url is None or url in seen:
            continue
        seen.add(url)
        selected.append(url)
        if len(selected) >= max_targets:
            break

    return selected
