"""Synthetic verifier gates; these tests never invoke the SDK or a model."""
from src.phase6_verification import verify


def test_isolation_failure_stops_before_evaluation(monkeypatch):
    monkeypatch.setattr('src.phase6_verification.verify_isolation',lambda **kwargs:{'status':'failed','error':{'code':'isolation_unverified','message':'Synthetic rejection'}})
    def forbidden(*args,**kwargs): raise AssertionError('No local model or inference should start')
    monkeypatch.setattr('src.embeddings.LocalEmbeddings',forbidden)
    report=verify(live=True)
    assert report['status']=='failed' and report['error']['code']=='isolation_unverified'
    assert 'evaluation' not in report


def test_metadata_only_verification_does_not_claim_live_evaluation(monkeypatch):
    monkeypatch.setattr('src.phase6_verification.verify_isolation',lambda **kwargs:{'status':'passed','access':{'model':'synthetic-metadata-only'}})
    report=verify()
    assert report['status']=='passed' and report['live_inference_requested'] is False
    assert 'evaluation' not in report


def test_existing_report_is_preserved_before_any_runtime_work(tmp_path):
    import subprocess,sys
    path=tmp_path/'existing.json'; path.write_text('fixture report')
    result=subprocess.run([sys.executable,'-m','src.phase6_verification','--report',str(path)],capture_output=True,text=True,timeout=10)
    assert result.returncode==2 and 'already exists' in result.stderr
    assert 'Traceback' not in result.stderr and path.read_text()=='fixture report'
