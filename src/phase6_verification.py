"""Explicit synthetic evaluation integration check; never sends public/private papers."""
import argparse
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile

from src.config import IngestionSettings
from src.evaluation.dataset import Question, freeze, label_for
from src.evaluation.runner import EvaluationRunner
from src.generation.isolation import EvidenceGateway
from src.phase3_verification import verify as verify_isolation


def verify(*, live=False):
    gateway = EvidenceGateway()
    report = {'phase':6,'checked_at_utc':datetime.now(timezone.utc).isoformat(),'status':'failed','live_inference_requested':live}
    try:
        access = verify_isolation(gateway=gateway)
        if access['status'] != 'passed':
            report['error'] = access.get('error',{'code':'isolation_unverified','message':'Existing isolation check failed.'})
            return report
        report['access'] = access['access']
        if live:
            import pymupdf
            from src.embeddings import LocalEmbeddings
            from src.ingestion.pipeline import PaperLibrary
            cache = IngestionSettings.from_environment()
            with tempfile.TemporaryDirectory(dir=gateway.settings.runtime_dir,prefix='synthetic-evaluation-') as folder:
                library = PaperLibrary(replace(cache,data_dir=Path(folder)),embeddings=LocalEmbeddings(cache))
                try:
                    document=pymupdf.open()
                    page=document.new_page()
                    page.insert_textbox(pymupdf.Rect(50,50,540,780),
                        'Synthetic Cobalt study. Cobalt achieved accuracy of 91.2 percent on SyntheticQA. '
                        'The baseline achieved 86.5 percent. Carbon emissions in kilograms of CO2 were not measured or reported.')
                    payload=document.tobytes(); document.close()
                    paper=library.ingest(payload,'synthetic-evaluation.pdf').paper
                    chunk=library.catalog.chunks()[0]
                    common={'split':'dev','paper_ids':[paper.paper_id],'rationale':'Generated fixture, not a scientific benchmark.'}
                    questions=[Question(**common,question_id='supported',kind='single_paper',question='What accuracy did Cobalt achieve on SyntheticQA?',answerable=True,
                                        expected_points=['91.2 percent.'],required_paper_ids=[paper.paper_id],relevant=[label_for(chunk)]),
                               Question(**common,question_id='missing',kind='unanswerable',question='What was the measured carbon footprint in kilograms of CO2?',answerable=False,
                                        expected_points=['The measurement was not reported.'])]
                    dataset=freeze(library,questions,name='synthetic-live-evaluation',synthetic=True)
                    runner=EvaluationRunner(library,gateway=gateway)
                    result=runner.run(dataset,generate=True,allow_remote=True,max_model_requests=6)
                    if (any(row['generation_status']!='generated' for row in result['rows'])
                            or any(row['answer']['status']!='answered' or not any('91.2' in claim['text'] for claim in row['answer']['claims'])
                                   for row in result['rows'] if row['question_id']=='supported')
                            or any(check['citation_validity']!=1 or check['correct_abstention_rate']!=1 for check in result['answer_checks'].values())):
                        raise RuntimeError('Synthetic verification mismatch')
                    again=runner.run(dataset,generate=True,allow_remote=True,max_model_requests=0)
                    if any(row['generation_status']!='cached' for row in again['rows']) or again['application_model_requests']!=0:
                        raise RuntimeError('Synthetic cache mismatch')
                    report['evaluation']={'modes':['bm25','vector','hybrid'],'questions':2,'cases':len(result['rows']),
                                          'application_model_requests':result['application_model_requests'],
                                          'cached_cases':len(again['rows']),'cache_reuse_model_requests':0,
                                          'canonical_citations':True,'missing_evidence_acknowledged':True,
                                          'semantic_scores':'not_claimed_without_human_review'}
                finally: library.close()
        report['status']='passed'
    except Exception:
        report['error']={'code':'verification_failed','message':'The synthetic evaluation check failed; no raw SDK or document details were logged.'}
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true',help='Use up to six application model requests for generated fixtures only; no benchmark paper is sent.')
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    if args.report and (args.report.exists() or args.report.is_symlink()):
        parser.error('The report already exists; choose a new filename. Existing reports are preserved.')
    try:
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
        report=verify(live=args.live)
        text=json.dumps(report,indent=2)
        if args.report:
            with args.report.open('x') as stream:
                stream.write(text+'\n')
        print(text)
    except KeyboardInterrupt:
        print(json.dumps({'status':'cancelled','message':'Synthetic evaluation verification was interrupted.'}))
        raise SystemExit(130)
    except OSError:
        print(json.dumps({'status':'failed','error':{'code':'report_write_failed','message':'The local verification report could not be saved; no raw paths were logged.'}}))
        raise SystemExit(1)
    raise SystemExit(0 if report['status']=='passed' else 1)


if __name__=='__main__': main()
