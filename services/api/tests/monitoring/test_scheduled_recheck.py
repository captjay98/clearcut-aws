import pytest
import uuid6
from clearcut.monitoring.adapters.unavailable_providers import (
    UnavailableExtractAdapter,
    UnavailableSearchAdapter,
)
from clearcut.monitoring.application.run_scheduled_watch import ScheduledWatchService
from clearcut.monitoring.domain.materiality import ChangeMateriality
from clearcut.monitoring.domain.models import (
    MonitoringRunStatus,
    WatchCadence,
    WatchConfig,
    WatchKind,
)
from clearcut.research.adapters.hermetic_extract import HermeticExtractAdapter
from clearcut.research.adapters.hermetic_search import HermeticSearchAdapter
from clearcut.research.domain.extraction import (
    ExtractBatchResponse,
    ExtractedPage,
    ExtractRequest,
)
from clearcut.research.domain.queries import SearchRequest
from clearcut.research.domain.snapshots import (
    ProviderFailure,
    ProviderResult,
    SearchResponse,
    SearchResultItem,
    SourceSnapshot,
)
from clearcut.research.ports.url_extract import ExtractResult, UrlExtractPort
from clearcut.research.ports.web_search import WebSearchPort


class StubExtractPort(UrlExtractPort):
    def __init__(self, result: ExtractResult) -> None:
        self.result = result
        self.calls: list[ExtractRequest] = []

    def extract(self, request: ExtractRequest) -> ExtractResult:
        self.calls.append(request)
        return self.result


class StubSearchPort(WebSearchPort):
    def __init__(self, result: ProviderResult) -> None:
        self.result = result
        self.calls: list[SearchRequest] = []

    def search(self, request: SearchRequest) -> ProviderResult:
        self.calls.append(request)
        return self.result


class RaisingExtractPort(UrlExtractPort):
    def extract(self, request: ExtractRequest) -> ExtractResult:
        raise RuntimeError("provider transport exploded")


@pytest.mark.asyncio
async def test_scheduled_watch_executes_recheck():
    extract_port = HermeticExtractAdapter()
    search_port = HermeticSearchAdapter()
    service = ScheduledWatchService(extract_port=extract_port, search_port=search_port)

    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    item_id = uuid6.uuid7()

    watch = WatchConfig.create(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        cadence=WatchCadence.DAILY,
        watch_kind=WatchKind.EXACT_SOURCE,
        target_url="https://uspto.gov/trademarks/coca-cola",
    )

    run, snapshot, delta = await service.execute_watch_recheck(watch)

    assert run.status == MonitoringRunStatus.COMPLETED
    assert snapshot.url == "https://uspto.gov/trademarks/coca-cola"
    assert snapshot.item_id == item_id
    # No prior snapshot was supplied, so there is nothing to compare and no
    # change signal is fabricated.
    assert delta is None


def _exact_source_watch(target_url: str | None = "https://uspto.gov/example") -> WatchConfig:
    return WatchConfig.create(
        org_id=uuid6.uuid7(),
        project_id=uuid6.uuid7(),
        item_id=uuid6.uuid7(),
        cadence=WatchCadence.DAILY,
        watch_kind=WatchKind.EXACT_SOURCE,
        target_url=target_url,
    )


def _extract_response(url: str, content: str) -> ExtractBatchResponse:
    return ExtractBatchResponse(
        extract_id="ext_stub_01",
        session_id="sess_stub",
        results=(ExtractedPage(url=url, title="Stub Title", content=content),),
        errors=(),
        warnings=(),
    )


@pytest.mark.asyncio
async def test_recheck_calls_provider_and_uses_returned_content():
    watch = _exact_source_watch()
    port = StubExtractPort(
        _extract_response(watch.target_url or "", "Real retrieved registration status v2")
    )
    service = ScheduledWatchService(extract_port=port, search_port=StubSearchPort(
        ProviderFailure(kind="retryable", message="unused")
    ))

    run, snapshot, delta = await service.execute_watch_recheck(watch)

    assert len(port.calls) == 1
    assert port.calls[0].urls == [watch.target_url]
    assert run.status == MonitoringRunStatus.COMPLETED
    assert snapshot is not None
    assert snapshot.origin == "extract"
    assert "Real retrieved registration status v2" in snapshot.excerpt
    assert "Active registered record" not in snapshot.excerpt
    assert delta is None  # no prior supplied


@pytest.mark.asyncio
async def test_recheck_material_delta_against_differing_prior():
    watch = _exact_source_watch()
    port = StubExtractPort(
        _extract_response(watch.target_url or "", "Source was cancelled")
    )
    service = ScheduledWatchService(extract_port=port, search_port=UnavailableSearchAdapter())
    prior = SourceSnapshot.create(
        org_id=watch.org_id,
        project_id=watch.project_id,
        item_id=watch.item_id,
        run_id=uuid6.uuid7(),
        url=watch.target_url or "",
        title="Prior",
        publisher="uspto.gov",
        excerpt="Source was active",
        origin="extract",
    )

    _run, _snapshot, delta = await service.execute_watch_recheck(watch, prior_snapshot=prior)

    assert delta is not None
    assert delta.materiality == ChangeMateriality.MATERIAL


@pytest.mark.asyncio
async def test_recheck_provider_failure_is_a_failed_run_without_snapshot():
    watch = _exact_source_watch()
    port = StubExtractPort(
        ProviderFailure(kind="authentication", message="Parallel API key rejected")
    )
    service = ScheduledWatchService(extract_port=port, search_port=UnavailableSearchAdapter())

    run, snapshot, delta = await service.execute_watch_recheck(watch)

    assert run.status == MonitoringRunStatus.FAILED
    assert run.error_message is not None
    assert "Parallel API key rejected" in run.error_message
    assert snapshot is None
    assert delta is None


@pytest.mark.asyncio
async def test_recheck_without_target_url_refuses_and_never_invents_one():
    watch = _exact_source_watch(target_url=None)
    port = StubExtractPort(_extract_response("https://never-called.example", "unused"))
    service = ScheduledWatchService(extract_port=port, search_port=UnavailableSearchAdapter())

    run, snapshot, delta = await service.execute_watch_recheck(watch)

    assert run.status == MonitoringRunStatus.FAILED
    assert run.error_message is not None
    assert "no target URL" in run.error_message
    assert snapshot is None
    assert port.calls == []


@pytest.mark.asyncio
async def test_recheck_raising_provider_is_a_failed_run():
    watch = _exact_source_watch()
    service = ScheduledWatchService(
        extract_port=RaisingExtractPort(), search_port=UnavailableSearchAdapter()
    )

    run, snapshot, _delta = await service.execute_watch_recheck(watch)

    assert run.status == MonitoringRunStatus.FAILED
    assert run.error_message is not None
    assert "provider transport exploded" in run.error_message
    assert snapshot is None


@pytest.mark.asyncio
async def test_event_topic_watch_searches_and_snapshots_first_result():
    watch = WatchConfig.create(
        org_id=uuid6.uuid7(),
        project_id=uuid6.uuid7(),
        item_id=uuid6.uuid7(),
        cadence=WatchCadence.WEEKLY,
        watch_kind=WatchKind.NEW_EVENT_TOPIC,
        query_text="new trademark filings Coca-Cola",
    )
    search = StubSearchPort(
        SearchResponse(
            search_id="s_stub",
            session_id="sess_stub",
            results=[
                SearchResultItem(
                    url="https://news.example/filing",
                    title="New filing reported",
                    publisher="news.example",
                    snippet="A new filing appeared this week.",
                )
            ],
        )
    )
    service = ScheduledWatchService(
        extract_port=UnavailableExtractAdapter(), search_port=search
    )

    run, snapshot, delta = await service.execute_watch_recheck(watch)

    assert len(search.calls) == 1
    assert search.calls[0].query == "new trademark filings Coca-Cola"
    assert run.status == MonitoringRunStatus.COMPLETED
    assert snapshot is not None
    assert snapshot.origin == "search"
    assert snapshot.url == "https://news.example/filing"
    assert "new filing appeared" in snapshot.excerpt
    assert delta is None


@pytest.mark.asyncio
async def test_event_topic_watch_with_no_results_completes_without_snapshot():
    watch = WatchConfig.create(
        org_id=uuid6.uuid7(),
        project_id=uuid6.uuid7(),
        item_id=uuid6.uuid7(),
        cadence=WatchCadence.WEEKLY,
        watch_kind=WatchKind.NEW_EVENT_TOPIC,
        query_text="quiet topic with no events",
    )
    search = StubSearchPort(
        SearchResponse(search_id="s_stub", session_id="sess_stub", results=[])
    )
    service = ScheduledWatchService(
        extract_port=UnavailableExtractAdapter(), search_port=search
    )

    run, snapshot, delta = await service.execute_watch_recheck(watch)

    assert len(search.calls) == 1
    assert run.status == MonitoringRunStatus.COMPLETED
    assert run.error_message is None
    assert snapshot is None
    assert delta is None


@pytest.mark.asyncio
async def test_unavailable_adapters_fail_closed():
    watch = _exact_source_watch()
    service = ScheduledWatchService(
        extract_port=UnavailableExtractAdapter(),
        search_port=UnavailableSearchAdapter(),
    )

    run, snapshot, delta = await service.execute_watch_recheck(watch)

    assert run.status == MonitoringRunStatus.FAILED
    assert run.error_message is not None
    assert "authorized research provider" in run.error_message
    assert snapshot is None
    assert delta is None
