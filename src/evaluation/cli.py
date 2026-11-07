"""Local evaluation commands. No model calls unless generation is explicitly enabled."""
import argparse
from dataclasses import replace
import json
import logging
from pathlib import Path

from filelock import Timeout

from src.config import IngestionSettings
from src.evaluation.artifacts import read_json, write_json
from src.evaluation.benchmark import prepare_public
from src.evaluation.dataset import EvaluationError, Question, freeze, load_dataset, save_dataset
from src.evaluation.faithfulness import HumanReview, review_metrics, review_template
from src.evaluation.runner import EvaluationRunner
from src.ingestion.pipeline import PaperLibrary
from src.embeddings import LocalEmbeddings
from src.schemas import IngestionError


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, help='Existing local library; use a separate directory for the public benchmark.')
    commands = parser.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser('prepare-public', help='Import locally downloaded versioned public PDFs and bind DRAFT labels; no inference.')
    prepare.add_argument('--pdf-dir', type=Path, required=True)
    prepare.add_argument('--spec-dir', type=Path, default=Path('eval'))
    prepare.add_argument('--output', type=Path, required=True)
    create = commands.add_parser('freeze', help='Freeze local canonical Question JSONL labels into a draft dataset.')
    create.add_argument('--questions', type=Path, required=True)
    create.add_argument('--name', required=True)
    create.add_argument('--output', type=Path, required=True)
    run = commands.add_parser('run', help='Evaluate BM25/vector/hybrid with shared budgets; retrieval only by default.')
    run.add_argument('--dataset', type=Path, required=True)
    run.add_argument('--output', type=Path, required=True)
    run.add_argument('--allow-draft', action='store_true', help='Exploratory scores only; never a reviewed benchmark.')
    run.add_argument('--split', choices=['all', 'dev', 'heldout'], default='all')
    run.add_argument('--generate', action='store_true')
    run.add_argument('--allow-remote', action='store_true', help='Permit selected questions/excerpts to the existing signed-in Codex gateway.')
    run.add_argument('--max-model-requests', type=int, default=0, help='Application turn cap, including retries. Default zero. Runtime-internal retries/usage are not token budgets.')
    inspect = commands.add_parser('inspect', help='List canonical chunk IDs/hashes for a PDF page.')
    inspect.add_argument('--paper', required=True)
    inspect.add_argument('--page', type=int, required=True)
    inspect.add_argument('--show-passages', action='store_true', help='Explicitly print private passage text locally; do not publish terminal output.')
    template = commands.add_parser('review-template', help='Prepare a pending human-review sheet; does not run a judge.')
    template.add_argument('--run', type=Path, required=True)
    template.add_argument('--output', type=Path, required=True)
    score = commands.add_parser('review-score', help='Score human atomic-claim judgments bound to an exact run artifact.')
    score.add_argument('--run', type=Path, required=True)
    score.add_argument('--review', type=Path, required=True)
    score.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    library = None
    try:
        if hasattr(args, 'output') and (args.output.exists() or args.output.is_symlink()):
            raise EvaluationError('The output already exists. Choose a new artifact path; existing files were preserved.')
        if args.command in {'review-template', 'review-score'}:
            report = read_json(args.run)
            if args.command == 'review-template':
                write_json(args.output, review_template(report).model_dump(mode='json'))
                print(json.dumps({'status': 'pending_human_review', 'model_requests': 0}))
            else:
                metrics = review_metrics(report, HumanReview.model_validate(read_json(args.review)))
                write_json(args.output, metrics)
                print(json.dumps({'status': 'human_review_scored', 'label_status': metrics['label_status'], 'metrics': metrics['metrics']}))
            return 0
        settings = IngestionSettings.from_environment()
        if args.data_dir is not None: settings = replace(settings, data_dir=args.data_dir)
        # Reuse the original public model cache even when a dedicated corpus
        # directory is selected. Embedding configuration remains identical.
        library = PaperLibrary(settings, embeddings=LocalEmbeddings(IngestionSettings.from_environment()))
        if args.command == 'prepare-public':
            dataset = prepare_public(library, args.pdf_dir, args.spec_dir)
            save_dataset(dataset, args.output)
            print(json.dumps({'status': 'draft_dataset_created', 'papers': len(dataset.paper_versions), 'questions': len(dataset.questions), 'model_requests': 0}))
        elif args.command == 'freeze':
            if args.questions.stat().st_size > 4_000_000:
                raise EvaluationError('The question file exceeds its size limit.')
            questions = [Question.model_validate_json(line) for line in args.questions.read_text().splitlines() if line.strip()]
            dataset = freeze(library, questions, name=args.name)
            save_dataset(dataset, args.output)
            print(json.dumps({'status': 'draft_dataset_created', 'questions': len(questions), 'model_requests': 0}))
        elif args.command == 'inspect':
            from src.evaluation.dataset import label_for
            for chunk in library.catalog.chunks(args.paper):
                if chunk.page_number == args.page:
                    value = label_for(chunk).model_dump(mode='json')
                    if args.show_passages: value['passage'] = chunk.text
                    print(json.dumps(value, ensure_ascii=False))
        else:
            report = EvaluationRunner(library).run(
                load_dataset(args.dataset), allow_draft=args.allow_draft, generate=args.generate,
                allow_remote=args.allow_remote, max_model_requests=args.max_model_requests, split=args.split,
            )
            write_json(args.output, report)
            failed = any(row['error_code'] not in (None, 'model_request_cap') for row in report['rows'])
            print(json.dumps({'status': 'partial_failure' if failed else 'completed',
                              'label_status': report['label_status'], 'cases': len(report['rows']),
                              'application_model_requests': report['application_model_requests'],
                              'generation_budget_exclusions': sum(row['generation_status'] == 'budget_exhausted' for row in report['rows']),
                              'semantic_metrics': 'pending_human_review',
                              'retrieval_at_10': {mode: {metric: stats[metric + '_at_10']['mean']
                                                        for metric in ('precision', 'recall', 'reciprocal_rank')}
                                                  for mode, stats in report['summary'].items()}}))
            return 1 if failed else 0
        return 0
    except (EvaluationError, IngestionError) as error:
        print(json.dumps({'status': 'failed', 'message': str(error)}))
        return 1
    except Timeout:
        print(json.dumps({'status': 'failed', 'message': 'The library is busy. Wait and retry evaluation.'}))
        return 1
    except KeyboardInterrupt:
        print(json.dumps({'status': 'cancelled', 'message': 'Evaluation was interrupted. Restart to recover any incomplete local operation.'}))
        return 130
    except Exception:
        print(json.dumps({'status': 'failed', 'message': 'Local evaluation failed. Check inputs, output paths, disk space and permissions; raw details were not logged.'}))
        return 1
    finally:
        if library is not None:
            try:
                library.close()
            except Exception:
                logging.getLogger(__name__).warning("evaluation_library_close_failed")


if __name__ == '__main__':
    raise SystemExit(main())
