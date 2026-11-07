from dataclasses import replace
from pathlib import Path
import hashlib,json

import pytest

from src.embeddings import LocalEmbeddings
from src.evaluation.dataset import EvaluationError
from src.evaluation.runner import EvaluationRunner
from src.evaluation.benchmark import prepare_public
from src.ingestion.pipeline import PaperLibrary
from evaluation_helpers import prepare_dataset


@pytest.mark.embedding_integration
def test_real_minilm_all_three_modes_over_same_frozen_corpus(settings,make_pdf):
    cache=replace(settings,data_dir=Path(__file__).resolve().parents[1]/'data')
    library=PaperLibrary(settings,embeddings=LocalEmbeddings(cache))
    try:
        dataset=prepare_dataset(library,make_pdf,comparison=True)
        report=EvaluationRunner(library).run(dataset)
        assert report['application_model_requests']==0
        assert all(row['error_code'] is None and row['retrieval']['context']['required_paper_coverage']==1 for row in report['rows'])
    finally: library.close()


def test_public_prepare_checks_hashes_before_modifying_library(library,make_pdf,tmp_path):
    root=Path(__file__).resolve().parents[1]/'eval'
    before=library.catalog.corpus_version()
    with pytest.raises(EvaluationError): prepare_public(library,tmp_path,root)
    assert library.catalog.corpus_version()==before and library.papers()==[]


def test_hybrid_comparison_keeps_previous_card_cache_identity(library,make_pdf):
    from dataclasses import asdict
    from src.config import MODEL
    from src.generation.comparison import ComparisonService
    from src.generation.prompts import CARD_PROMPT_VERSION
    dataset=prepare_dataset(library,make_pdf,comparison=True)
    service=ComparisonService(library)
    evidence=service.collect(dataset.questions[0].question,dataset.questions[0].paper_ids,dataset.questions[0].categories)
    paper=evidence.papers[0]
    previous={'paper_id':paper.paper.paper_id,'paper_version':paper.paper_version,'question':evidence.question,
              'categories':evidence.categories,'model':MODEL,'prompt_version':CARD_PROMPT_VERSION,'settings':asdict(service.settings),
              'sources':{category:[chunk.chunk_id for chunk in context.snapshot.documents] for category,context in paper.contexts.items()}}
    assert service.cache_key(paper,evidence)==hashlib.sha256(json.dumps(previous,sort_keys=True).encode()).hexdigest()
    sparse=service.collect(evidence.question,dataset.questions[0].paper_ids,evidence.categories,mode='bm25')
    assert service.cache_key(sparse.papers[0],sparse)!=service.cache_key(paper,evidence)
