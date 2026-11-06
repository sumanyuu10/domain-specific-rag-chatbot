"""Explicit synthetic multi-paper comparison verification; never uses private PDFs."""
import argparse
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile

from src.config import IngestionSettings, Settings
from src.generation.comparison import ComparisonService
from src.generation.isolation import EvidenceGateway
from src.generation.llm import CodexIntegrationError
from src.phase3_verification import verify as verify_isolation
from src.schemas import RetrievalError


class CountingGateway(EvidenceGateway):
    calls = 0

    async def generate(self, *args, **kwargs):
        self.calls += 1
        return await super().generate(*args, **kwargs)


def verify(*, live=False):
    gateway = CountingGateway(Settings.from_environment())
    report = {
        "phase": 4, "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "failed", "live_inference_requested": live, "checks": {},
    }
    try:
        isolation = verify_isolation(gateway=gateway)
        if isolation["status"] != "passed":
            report["error"] = isolation.get("error", {"code": "isolation_unverified", "message": "Worker verification failed."})
            return report
        report["access"] = isolation["access"]
        report["checks"]["existing_worker_isolation"] = True
        if live:
            report["comparison"] = verify_comparison(gateway)
            report["checks"].update(
                per_paper_category_coverage=True, canonical_source_citations=True,
                agreement_and_disagreement=True, missing_category_acknowledged=True,
                validated_card_cache_reused=True,
            )
        report["status"] = "passed"
    except (CodexIntegrationError, RetrievalError) as error:
        report["error"] = {"code": getattr(error, "code", "comparison_failed"), "message": str(error)}
    except Exception:
        report["error"] = {"code": "verification_failed", "message": "The synthetic comparison check failed; raw model/runtime details were not logged."}
    return report


def verify_comparison(gateway):
    import pymupdf
    from src.embeddings import LocalEmbeddings
    from src.ingestion.pipeline import PaperLibrary
    cache = IngestionSettings.from_environment()
    texts = [
        "Synthetic Cobalt study. Methodology: Cobalt uses a transformer with self-attention. "
        "Task: question answering. Dataset: ProbeQA. Split: held-out test. Metric: accuracy percent. "
        "Value: 91.2 percent. Settings: fixed sample budget and fixed evaluation code. "
        "Conclusion: the authors state that attention is necessary for generalization on this task. "
        "Limitations: this study evaluates English examples only.",
        "Synthetic Amber study. Methodology: Amber uses an MLP without attention. "
        "Task: question answering. Dataset: ProbeQA. Split: held-out test. Metric: accuracy percent. "
        "Value: 87.0 percent. Settings: fixed sample budget and fixed evaluation code. "
        "Conclusion: the authors state that attention is not necessary for generalization on this task.",
    ]
    with tempfile.TemporaryDirectory(dir=gateway.settings.runtime_dir, prefix="synthetic-comparison-") as folder:
        library = PaperLibrary(replace(cache, data_dir=Path(folder)), embeddings=LocalEmbeddings(cache))
        try:
            ids = []
            for number, text in enumerate(texts):
                document = pymupdf.open()
                page = document.new_page()
                page.insert_textbox(pymupdf.Rect(50, 50, 540, 780), text, fontsize=10)
                payload = document.tobytes()
                document.close()
                ids.append(library.ingest(payload, f"synthetic-study-{number}.pdf").paper.paper_id)
            service = ComparisonService(library, gateway=gateway)
            evidence = service.collect(
                "Compare the studies in all categories. Identify the shared dataset and contradictory author conclusions about whether attention is necessary.", ids,
            )
            result = service.compare(evidence, allow_remote=True)
            missing = next(cell for cell in result.cells if cell.paper_id == ids[1] and cell.category == "limitations") if result.cells else None
            if (result.status != "completed" or len(result.cells) != 10
                    or {citation.paper_id for citation in result.citations} != set(ids)
                    or any(citation.page_number != 1 for citation in result.citations)
                    or not {"agreement", "disagreement"} <= {relation.kind for relation in result.relationships}
                    or not missing or missing.status != "missing"):
                raise CodexIntegrationError("verification_mismatch", "The synthetic multi-paper comparison or missing-category check failed.")
            for relation in result.relationships:
                cited_papers = {citation.paper_id for citation in result.citations if citation.source_id in relation.source_ids}
                if not set(relation.paper_ids) <= cited_papers:
                    raise CodexIntegrationError("verification_mismatch", "A comparison relationship did not resolve to all named original papers.")
            before = gateway.calls
            again = service.compare(evidence, allow_remote=True)
            if again.status != "completed" or set(again.cached_paper_ids) != set(ids) or not 1 <= gateway.calls - before <= 2:
                raise CodexIntegrationError("verification_mismatch", "Cached cards were not reused on the second comparison.")
            return {
                "model": result.model, "paper_count": 2, "category_count": 5,
                "cell_count": len(result.cells), "citation_count": len(result.citations),
                "relationship_kinds": sorted({relation.kind for relation in result.relationships}),
                "reused_card_count": len(again.cached_paper_ids), "generation_requests": gateway.calls,
            }
        finally:
            library.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Use signed-in Codex allowance for synthetic comparison and cache checks (normally four model turns, up to eight with bounded retries/repairs).")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = verify(live=args.live)
    text = json.dumps(report, indent=2)
    print(text)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n")
    raise SystemExit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
