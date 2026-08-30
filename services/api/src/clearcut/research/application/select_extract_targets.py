from clearcut.research.domain.snapshots import SearchResultItem


def select_extract_targets(
    search_results: list[SearchResultItem],
    max_targets: int = 3,
) -> list[str]:
    seen: set[str] = set()
    selected: list[str] = []

    for item in search_results:
        url = item.url.strip()
        # Enforce secure HTTPS only
        if not url.startswith("https://"):
            continue
        # Remove canonical duplicates
        if url in seen:
            continue
        seen.add(url)
        selected.append(url)
        if len(selected) >= max_targets:
            break

    return selected
