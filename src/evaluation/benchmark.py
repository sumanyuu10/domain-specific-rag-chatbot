"""Bind public-paper draft definitions to the existing local canonical corpus."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from src.evaluation.dataset import EvaluationError, Question, freeze, label_for


def prepare_public(library, pdf_directory, specification_directory):
    root, specs = Path(pdf_directory), Path(specification_directory)
    try:
        papers = json.loads((specs / "papers.json").read_text())
        records = [json.loads(line) for line in (specs / "questions.jsonl").read_text().splitlines() if line.strip()]
        if (len(papers) != 6 or len({paper['key'] for paper in papers}) != 6
                or len(records) != 30 or Counter(record['kind'] for record in records)
                != {'single_paper': 12, 'comparison': 8, 'unanswerable': 5, 'misleading': 5}
                or Counter(record['split'] for record in records) != {'dev': 10, 'heldout': 20}):
            raise EvaluationError("The public benchmark specification must contain six papers and the approved 30-question split.")
        # Validate all bytes before importing anything. The benchmark gets a
        # dedicated library; an existing user's private corpus is not changed.
        payloads = {}
        for paper in papers:
            key = paper['key']
            if not re.fullmatch(r'[a-z0-9_-]+', key):
                raise EvaluationError("Invalid public-paper alias.")
            path = root / (key + '.pdf')
            if path.is_symlink() or path.stat().st_size > library.settings.max_file_bytes:
                raise EvaluationError("Unsupported public PDF path or size.")
            payload = path.read_bytes()
            if hashlib.sha256(payload).hexdigest() != paper['sha256']:
                raise EvaluationError("A public PDF differs from the documented version/hash; inspect it before rebinding labels.")
            payloads[key] = payload
        existing = {paper.paper_id for paper in library.papers()}
        expected = {hashlib.sha256(payload).hexdigest() for payload in payloads.values()}
        if not existing <= expected:
            raise EvaluationError("Use a dedicated public-benchmark data directory, not a library containing other papers.")
        ids = {key: library.ingest(payload, key + '.pdf').paper.paper_id for key, payload in payloads.items()}
        questions = []
        for record in records:
            labels = []
            for reference in record['evidence']:
                paper_id = ids[reference['paper']]
                chunks = [chunk for chunk in library.catalog.chunks(paper_id) if chunk.page_number == reference['page']]
                terms = [term.casefold() for term in reference['terms']]
                if not chunks or not terms:
                    raise EvaluationError("A proposed evidence page has no canonical chunks or lexical anchors.")
                score = lambda chunk: sum(term in chunk.text.casefold() for term in terms)
                # Proposed anchors are a reproducible starting point, not human
                # relevance judgments. The resulting dataset stays explicitly draft.
                chunk = max(chunks, key=lambda chunk: (score(chunk), -chunk.chunk_ordinal))
                if score(chunk) == 0:
                    raise EvaluationError("No lexical anchor matched on a proposed evidence page; inspect the PDF version.")
                label = label_for(chunk, reference['category'])
                if label not in labels: labels.append(label)
            selected = [ids[key] for key in record['papers']]
            questions.append(Question(
                **{key: record[key] for key in ('question_id', 'question', 'kind', 'task', 'split', 'categories', 'answerable', 'expected_points', 'rationale')},
                paper_ids=selected, required_paper_ids=selected if record['answerable'] else [], relevant=labels,
            ))
        return freeze(library, questions, name='public-six-v1')
    except EvaluationError:
        raise
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise EvaluationError("Public benchmark preparation failed. Check the versioned PDFs and draft specification; no raw details were logged.") from error
