import json
import pytest

from src.evaluation.dataset import Dataset, EvaluationError, Question, load_dataset, save_dataset, validate_dataset
from evaluation_helpers import prepare_dataset


def test_draft_requires_human_review_and_cannot_claim_fake_reviewer(library,make_pdf):
    dataset=prepare_dataset(library,make_pdf)
    value=dataset.model_dump()
    value.update(purpose='literature_benchmark',review_status='draft')
    draft=Dataset.model_validate(value)
    with pytest.raises(EvaluationError,match='human review'): validate_dataset(library,draft)
    validate_dataset(library,draft,allow_draft=True)
    value.update(review_status='reviewed')
    with pytest.raises(ValueError): Dataset.model_validate(value)
    value.update(reviewer='Human reviewer fixture',reviewed_at='2026-11-07T12:00:00Z')
    validate_dataset(library,Dataset.model_validate(value))


@pytest.mark.parametrize('damage',['duplicate','unknown_paper','page','content','corpus','fingerprint'])
def test_stale_or_invalid_labels_are_rejected(library,make_pdf,damage):
    dataset=prepare_dataset(library,make_pdf)
    value=dataset.model_dump()
    if damage=='duplicate':
        value['questions'].append(value['questions'][0])
        with pytest.raises(ValueError): Dataset.model_validate(value)
        return
    if damage=='unknown_paper':
        value['questions'][0]['paper_ids']=['a'*64]
        with pytest.raises(ValueError): Dataset.model_validate(value)
        return
    if damage=='page': value['questions'][0]['relevant'][0]['page_number']=999
    if damage=='content': value['questions'][0]['relevant'][0]['passage_sha256']='a'*64
    if damage=='corpus': library.catalog.bump_revision()
    if damage=='fingerprint': value['pipeline_fingerprint']='wrong'
    with pytest.raises(EvaluationError): validate_dataset(library,Dataset.model_validate(value))


@pytest.mark.parametrize('damage',['no_gold','foreign_category','duplicate_scope','no_required'])
def test_question_scope_and_answerability_contract(library,make_pdf,damage):
    value=prepare_dataset(library,make_pdf).questions[0].model_dump()
    if damage=='no_gold': value['relevant']=[]
    if damage=='foreign_category': value['relevant'][0]['category']='datasets'
    if damage=='duplicate_scope': value['paper_ids']*=2
    if damage=='no_required': value['required_paper_ids']=[]
    with pytest.raises(ValueError): Question.model_validate(value)


def test_dataset_io_never_overwrites_and_errors_are_safe(library,make_pdf,tmp_path):
    dataset=prepare_dataset(library,make_pdf)
    path=tmp_path/'dataset.json'
    save_dataset(dataset,path)
    assert load_dataset(path)==dataset
    with pytest.raises(FileExistsError): save_dataset(dataset,path)
    path.write_text('PRIVATE broken fixture')
    with pytest.raises(EvaluationError) as caught: load_dataset(path)
    assert 'PRIVATE' not in str(caught.value)
