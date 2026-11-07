import json
from pathlib import Path

from src.evaluation.cli import main
from src.evaluation.dataset import save_dataset
from evaluation_helpers import prepare_dataset


def test_cli_retrieval_only_and_safe_output(library,make_pdf,tmp_path,monkeypatch,capsys):
    dataset=prepare_dataset(library,make_pdf)
    path=tmp_path/'dataset.json'; save_dataset(dataset,path)
    output=tmp_path/'run.json'
    monkeypatch.setattr('src.evaluation.cli.PaperLibrary',lambda *args,**kwargs:library)
    assert main(['run','--dataset',str(path),'--output',str(output)])==0
    stdout=capsys.readouterr().out
    assert 'What accuracy' not in stdout and '91.2' not in stdout
    assert json.loads(stdout)['application_model_requests']==0
    assert output.exists()
    assert main(['run','--dataset',str(path),'--output',str(output)])==1
    assert 'already exists' in capsys.readouterr().out


def test_cli_errors_do_not_expose_private_paths(tmp_path,capsys):
    code=main(['review-template','--run',str(tmp_path/'PRIVATE-missing-file'),'--output',str(tmp_path/'sheet.json')])
    assert code==1
    assert 'PRIVATE' not in capsys.readouterr().out


def test_cli_keyboard_interrupt_is_sanitized(tmp_path,monkeypatch,capsys):
    def interrupt(*args): raise KeyboardInterrupt
    monkeypatch.setattr('src.evaluation.cli.read_json',interrupt)
    assert main(['review-template','--run','fixture','--output',str(tmp_path/'sheet.json')])==130
    assert json.loads(capsys.readouterr().out)['status']=='cancelled'


def test_public_spec_matches_approved_question_mix():
    root=Path(__file__).resolve().parents[1]/'eval'
    from collections import Counter
    papers=json.loads((root/'papers.json').read_text())
    questions=[json.loads(line) for line in (root/'questions.jsonl').read_text().splitlines()]
    assert len(papers)==6 and len(questions)==30
    assert Counter(question['kind'] for question in questions)=={'single_paper':12,'comparison':8,'unanswerable':5,'misleading':5}
    assert Counter(question['split'] for question in questions)=={'dev':10,'heldout':20}
    assert all(paper['redistribute_pdf'] is False for paper in papers)


def test_cleanup_error_does_not_expose_raw_details(library,make_pdf,tmp_path,monkeypatch,capsys,caplog):
    dataset=prepare_dataset(library,make_pdf)
    path=tmp_path/'dataset.json'; save_dataset(dataset,path)
    monkeypatch.setattr('src.evaluation.cli.PaperLibrary',lambda *args,**kwargs:library)
    def fail(): raise RuntimeError('PRIVATE cleanup fixture')
    monkeypatch.setattr(library,'close',fail)
    assert main(['run','--dataset',str(path),'--output',str(tmp_path/'run.json')])==0
    assert 'PRIVATE' not in capsys.readouterr().out + caplog.text
    # Restore before the shared fixture's normal teardown.
    monkeypatch.undo()
