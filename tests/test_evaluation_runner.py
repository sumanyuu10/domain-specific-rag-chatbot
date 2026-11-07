import pytest

from src.evaluation.artifacts import validate_result
from src.evaluation.dataset import EvaluationError
from src.evaluation.runner import EvaluationRunner
from src.generation.llm import CodexIntegrationError
from evaluation_helpers import EvaluationGateway,prepare_dataset


@pytest.mark.parametrize('comparison',[False,True])
def test_three_modes_real_indexes_and_bounded_context(library,make_pdf,comparison):
    dataset=prepare_dataset(library,make_pdf,comparison=comparison,many=True)
    gateway=EvaluationGateway()
    report=EvaluationRunner(library,gateway=gateway).run(dataset)
    assert len(report['rows'])==3 and gateway.calls==0
    assert report['application_model_requests']==0
    assert all(row['error_code'] is None for row in report['rows'])
    for row in report['rows']:
        assert row['answer'] is None
        assert row['retrieval']['units']
        assert report['answer_checks'][row['mode']]['faithfulness'] is None
        for unit in row['retrieval']['units']:
            assert len(unit['context_ids']) <= (2 if comparison else 8)
            assert len(unit['ranked_ids']) > len(unit['context_ids'])


@pytest.mark.parametrize('comparison',[False,True])
def test_generation_and_exact_result_cache_reuse(library,make_pdf,comparison):
    dataset=prepare_dataset(library,make_pdf,comparison=comparison)
    gateway=EvaluationGateway()
    runner=EvaluationRunner(library,gateway=gateway)
    report=runner.run(dataset,generate=True,allow_remote=True,max_model_requests=20)
    assert all(row['generation_status']=='generated' for row in report['rows'])
    assert report['application_model_requests']==(9 if comparison else 3)
    again=runner.run(dataset,generate=True,allow_remote=True,max_model_requests=0)
    assert again['application_model_requests']==0
    assert all(row['generation_status']=='cached' for row in again['rows'])
    assert all(value['citation_validity']==1 for value in again['answer_checks'].values())


def test_generation_requires_consent_and_stops_at_cap(library,make_pdf):
    dataset=prepare_dataset(library,make_pdf)
    gateway=EvaluationGateway()
    runner=EvaluationRunner(library,gateway=gateway)
    with pytest.raises(EvaluationError,match='consent'): runner.run(dataset,generate=True,max_model_requests=3)
    result=runner.run(dataset,generate=True,allow_remote=True,max_model_requests=1)
    assert result['application_model_requests']==1 and gateway.calls==1
    assert [row['generation_status'] for row in result['rows']]==['generated','budget_exhausted','budget_exhausted']
    assert all(row['retrieval'] is not None for row in result['rows'])


def test_invalid_cached_artifact_is_regenerated_within_cap(library,make_pdf):
    dataset=prepare_dataset(library,make_pdf)
    gateway=EvaluationGateway()
    runner=EvaluationRunner(library,gateway=gateway)
    runner.run(dataset,generate=True,allow_remote=True,max_model_requests=3)
    path=next((library.settings.data_dir/'evaluation'/'answer_cache').glob('*.json'))
    path.write_text('{"corrupt":"fixture"}')
    result=runner.run(dataset,generate=True,allow_remote=True,max_model_requests=1)
    assert result['application_model_requests']==1
    assert sum(row['generation_status']=='cached' for row in result['rows'])==2


def test_quota_failure_halts_generation_but_retains_retrieval(library,make_pdf,caplog):
    dataset=prepare_dataset(library,make_pdf)
    gateway=EvaluationGateway()
    gateway.qa.answers=[CodexIntegrationError('quota_exceeded','Safe quota message')]
    result=EvaluationRunner(library,gateway=gateway).run(dataset,generate=True,allow_remote=True,max_model_requests=10)
    assert result['application_model_requests']==1
    assert all(row['generation_status']=='failed' and row['retrieval'] for row in result['rows'])
    assert 'Safe quota message' not in caplog.text


def test_corpus_change_during_generation_aborts_run(library,make_pdf):
    dataset=prepare_dataset(library,make_pdf)
    gateway=EvaluationGateway()
    gateway.qa.callback=library.catalog.bump_revision
    with pytest.raises(EvaluationError,match='corpus changed'):
        EvaluationRunner(library,gateway=gateway).run(dataset,generate=True,allow_remote=True,max_model_requests=3)


def test_human_label_review_does_not_spend_again_for_unchanged_prompts(library,make_pdf):
    from src.evaluation.dataset import Dataset
    original=prepare_dataset(library,make_pdf).model_dump()
    original.update(purpose='literature_benchmark',review_status='draft')
    draft=Dataset.model_validate(original)
    gateway=EvaluationGateway(); runner=EvaluationRunner(library,gateway=gateway)
    first=runner.run(draft,allow_draft=True,generate=True,allow_remote=True,max_model_requests=3)
    reviewed=Dataset.model_validate({**original,'review_status':'reviewed','reviewer':'Synthetic test reviewer','reviewed_at':'2026-11-07'})
    second=runner.run(reviewed,generate=True,allow_remote=True,max_model_requests=0)
    assert second['identity']['dataset_sha256']!=first['identity']['dataset_sha256']
    assert second['application_model_requests']==0 and all(row['generation_status']=='cached' for row in second['rows'])


def test_repair_attempts_consume_the_same_model_budget(library,make_pdf):
    from test_answer_chain import valid_answer
    dataset=prepare_dataset(library,make_pdf)
    gateway=EvaluationGateway(); gateway.qa.answers=['not JSON',valid_answer()]
    report=EvaluationRunner(library,gateway=gateway).run(dataset,generate=True,allow_remote=True,max_model_requests=2)
    assert report['application_model_requests']==2 and gateway.calls==2
    assert [row['generation_status'] for row in report['rows']]==['generated','budget_exhausted','budget_exhausted']
    assert report['rows'][0]['answer']['repaired'] is True
