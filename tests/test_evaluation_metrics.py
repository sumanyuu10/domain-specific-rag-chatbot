import pytest

from src.evaluation.retrieval_metrics import ranked_metrics, context_metrics, describe


@pytest.mark.parametrize('ranked,gold,k,precision,recall,rr', [
    (['a','b'], {'b'}, 5, .2, 1., .5),
    ([], {'a'}, 5, 0., 0., 0.),
    (['a'], {'a','b'}, 5, .2, .5, 1.),
    (['a','a','b'], {'b'}, 2, .5, 1., .5),
    (['x','a'], {'a'}, 1, 0., 0., 0.),
    (['a'], set(), 5, None, None, None),
])
def test_ranked_metrics_explicit_denominators(ranked,gold,k,precision,recall,rr):
    result = ranked_metrics(ranked,gold,k=k)
    assert result['precision'] == precision and result['recall'] == recall and result['reciprocal_rank'] == rr


@pytest.mark.parametrize('k',[0,-1,True,1.5])
def test_invalid_k(k):
    with pytest.raises(ValueError): ranked_metrics([],[],k=k)


def test_irrelevant_paper_presence_does_not_earn_evidence_coverage(library,make_pdf):
    first=library.ingest(make_pdf(title='A'),'a.pdf').paper
    second=library.ingest(make_pdf(title='B'),'b.pdf').paper
    chunks=library.catalog.chunks()
    gold={library.catalog.chunks(first.paper_id)[0].chunk_id}
    result=context_metrics(chunks,gold,[first.paper_id,second.paper_id])
    assert result['paper_coverage']==.5
    assert describe([None,0,1])=={'count':2,'mean':.5,'median':.5,'minimum':0,'maximum':1}
