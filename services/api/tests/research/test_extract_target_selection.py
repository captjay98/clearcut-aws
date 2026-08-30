from clearcut.research.application.select_extract_targets import select_extract_targets
from clearcut.research.domain.snapshots import SearchResultItem


def test_extract_target_selection_limits_to_three_canonical_https():
    results = [
        SearchResultItem(
            url="https://uspto.gov/tm1",
            title="USPTO 1",
            publisher="USPTO",
            snippet="s1",
        ),
        SearchResultItem(
            url="http://insecure.org/page",
            title="Insecure",
            publisher="Insecure",
            snippet="s2",
        ),
        SearchResultItem(
            url="https://uspto.gov/tm1",
            title="Duplicate",
            publisher="USPTO",
            snippet="s3",
        ),
        SearchResultItem(
            url="https://news.com/article1",
            title="News 1",
            publisher="News",
            snippet="s4",
        ),
        SearchResultItem(
            url="https://news.com/article2",
            title="News 2",
            publisher="News",
            snippet="s5",
        ),
        SearchResultItem(
            url="https://news.com/article3",
            title="News 3",
            publisher="News",
            snippet="s6",
        ),
    ]

    selected = select_extract_targets(results, max_targets=3)
    assert len(selected) <= 3
    assert selected == [
        "https://uspto.gov/tm1",
        "https://news.com/article1",
        "https://news.com/article2",
    ]
    for url in selected:
        assert url.startswith("https://")
