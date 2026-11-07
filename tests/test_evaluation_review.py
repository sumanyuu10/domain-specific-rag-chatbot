import json
import pytest

from src.evaluation.dataset import EvaluationError
from src.evaluation.faithfulness import HumanReview, review_template, review_metrics, answer_checks
from src.evaluation.runner import EvaluationRunner
from evaluation_helpers import EvaluationGateway,prepare_dataset


def generated(library,make_pdf,unanswerable=False):
    dataset=prepare_dataset(library,make_pdf,unanswerable=unanswerable)
    gateway=EvaluationGateway()
    if unanswerable: gateway.qa.answers=[json.dumps({'status':'insufficient_evidence','claims':[],'missing_information':['Not in the synthetic evidence.']})]
    return EvaluationRunner(library,gateway=gateway).run(dataset,generate=True,allow_remote=True,max_model_requests=3)


def test_semantic_scores_need_human_review_and_atomic_coverage(library,make_pdf):
    report=generated(library,make_pdf)
    sheet=review_template(report)
    assert all(answer.claims[0].units[0].verdict=='pending' for answer in sheet.answers)
    with pytest.raises(EvaluationError,match='human reviewer'): review_metrics(report,sheet)
    sheet.reviewer='Synthetic test reviewer'
    sheet.reviewed_at='2026-11-07T12:00:00Z'
    metrics=review_metrics(report,sheet)['metrics']
    assert all(value['faithfulness'] is None and value['parent_review_coverage']==0 for value in metrics.values())
    for answer in sheet.answers:
        answer.answer_relevance='relevant'
        claim=answer.claims[0]; claim.atomic_coverage_confirmed=True
        claim.units[0].verdict='supported'
        claim.units[0].citation_support={'S1':'supports'}
    metrics=review_metrics(report,sheet)['metrics']
    assert all(value['faithfulness']==1 and value['citation_support_correctness']==1 and value['hallucination_rate']==0 for value in metrics.values())


def test_unsupported_and_uncertain_claims_have_explicit_denominators(library,make_pdf):
    report=generated(library,make_pdf)
    sheet=review_template(report)
    sheet.reviewer='Synthetic fixture reviewer'; sheet.reviewed_at='2026-11-07'
    from src.evaluation.faithfulness import AtomicReview
    for answer in sheet.answers:
        claim=answer.claims[0]; claim.atomic_coverage_confirmed=True
        claim.units=[AtomicReview(text='Supported synthetic fact',verdict='supported',citation_support={'S1':'supports'}),
                     AtomicReview(text='Unsupported synthetic fact',verdict='unsupported',citation_support={'S1':'does_not_support'}),
                     AtomicReview(text='Uncertain synthetic fact',verdict='uncertain',citation_support={'S1':'uncertain'})]
    metrics=review_metrics(report,sheet)['metrics']['hybrid']
    assert metrics['faithfulness']==.5 and metrics['hallucination_rate']==.5
    assert metrics['atomic_review_coverage']==pytest.approx(2/3) and metrics['assessed_factual_claims']==2
    assert metrics['citation_support_correctness']==.5 and metrics['citation_unassessed']==1


@pytest.mark.parametrize('damage',['artifact','run_id','foreign_source','duplicate_answer','missing_claim'])
def test_review_identity_and_scope_rejected(library,make_pdf,damage):
    report=generated(library,make_pdf)
    sheet=review_template(report)
    sheet.reviewer='Synthetic reviewer'; sheet.reviewed_at='2026-11-07'
    if damage=='artifact': report['rows'][0]['question_id']='changed'
    if damage=='run_id': sheet.run_id='foreign'
    if damage=='foreign_source':
        sheet.answers[0].claims[0].atomic_coverage_confirmed=True
        sheet.answers[0].claims[0].units[0].citation_support={'S999':'supports'}
    if damage=='duplicate_answer': sheet.answers.append(sheet.answers[0])
    if damage=='missing_claim': sheet.answers[0].claims=[]
    with pytest.raises(EvaluationError): review_metrics(report,sheet)


def test_no_factual_claims_never_earn_perfect_faithfulness(library,make_pdf):
    report=generated(library,make_pdf,unanswerable=True)
    checks=answer_checks(report)
    assert all(value['correct_abstention_rate']==1 and value['faithfulness'] is None for value in checks.values())
    sheet=review_template(report); sheet.reviewer='Synthetic reviewer'; sheet.reviewed_at='2026-11-07'
    metrics=review_metrics(report,sheet)['metrics']
    assert all(value['faithfulness'] is None and value['assessed_factual_claims']==0 for value in metrics.values())
