"""Validated card persistence, selective reuse and deletion invalidation."""
from src.generation.comparison import ComparisonService
from src.ingestion.pipeline import PaperLibrary
from conftest import NoEmbeddings
from comparison_helpers import FakeComparisonGateway


def test_cards_survive_reopening_without_reembedding(settings, embeddings, make_pdf):
    first = PaperLibrary(settings, embeddings=embeddings)
    try:
        ids = [first.ingest(make_pdf(title=str(number)), f"paper-{number}.pdf").paper.paper_id for number in range(2)]
        service = ComparisonService(first, gateway=FakeComparisonGateway())
        evidence = service.collect("Compare methodology", ids, ["methodology"])
        service.compare(evidence, allow_remote=True)
    finally:
        first.close()
    second = PaperLibrary(settings, embeddings=NoEmbeddings())
    gateway = FakeComparisonGateway()
    try:
        result = ComparisonService(second, gateway=gateway).compare(evidence, allow_remote=True)
        assert result.status == "completed" and set(result.cached_paper_ids) == set(ids)
        assert [kind for kind, _request in gateway.calls] == ["synthesis"]
    finally:
        second.close()


def test_delete_cascades_only_affected_cached_cards(library, make_pdf):
    ids = [library.ingest(make_pdf(title=str(number)), f"paper-{number}.pdf").paper.paper_id for number in range(2)]
    service = ComparisonService(library, gateway=FakeComparisonGateway())
    evidence = service.collect("", ids)
    service.compare(evidence, allow_remote=True)
    library.delete(ids[0])
    with library.catalog.connection() as db:
        rows = db.execute("SELECT paper_id FROM comparison_cards").fetchall()
    assert [row[0] for row in rows] == [ids[1]]


def test_corrupt_card_is_regenerated_without_discarding_other_cards(library, make_pdf):
    ids = [library.ingest(make_pdf(title=str(number)), f"paper-{number}.pdf").paper.paper_id for number in range(2)]
    gateway = FakeComparisonGateway()
    service = ComparisonService(library, gateway=gateway)
    evidence = service.collect("", ids)
    service.compare(evidence, allow_remote=True)
    key = service.cache_key(evidence.papers[0], evidence)
    with library.catalog.connection() as db:
        db.execute("UPDATE comparison_cards SET card_json=? WHERE cache_key=?", ("corrupt JSON", key))
    result = service.compare(evidence, allow_remote=True)
    assert result.status == "completed" and len(result.cached_paper_ids) == 1
    assert [kind for kind, _request in gateway.calls][-2:] == ["card", "synthesis"]


def test_prompt_version_changes_invalidate_cards(library, make_pdf, monkeypatch):
    ids = [library.ingest(make_pdf(title=str(number)), f"paper-{number}.pdf").paper.paper_id for number in range(2)]
    service = ComparisonService(library, gateway=FakeComparisonGateway())
    evidence = service.collect("", ids)
    service.compare(evidence, allow_remote=True)
    monkeypatch.setattr("src.generation.comparison.CARD_PROMPT_VERSION", "new-test-prompt-version")
    result = service.compare(evidence, allow_remote=True)
    assert not result.cached_paper_ids
    assert all(card.prompt_version == "new-test-prompt-version" for card in result.cards)


def test_changed_selection_can_reuse_the_same_paper_card(library, make_pdf):
    ids = [library.ingest(make_pdf(title=str(number)), f"paper-{number}.pdf").paper.paper_id for number in range(3)]
    service = ComparisonService(library, gateway=FakeComparisonGateway())
    service.compare(service.collect("", ids[:2]), allow_remote=True)
    result = service.compare(service.collect("", ids[1:]), allow_remote=True)
    assert result.cached_paper_ids == [ids[1]]


def test_cache_retention_is_bounded_per_paper(library, make_pdf):
    from src.config import ComparisonSettings
    ids = [library.ingest(make_pdf(title=str(number)), f"paper-{number}.pdf").paper.paper_id for number in range(2)]
    service = ComparisonService(library, gateway=FakeComparisonGateway(), settings=ComparisonSettings(cached_cards_per_paper=2))
    for focus in ("focus one", "focus two", "focus three"):
        service.compare(service.collect(focus, ids, ["methodology"]), allow_remote=True)
    with library.catalog.connection() as db:
        counts = db.execute("SELECT paper_id,count(*) FROM comparison_cards GROUP BY paper_id").fetchall()
    assert len(counts) == 2 and all(row[1] == 2 for row in counts)
