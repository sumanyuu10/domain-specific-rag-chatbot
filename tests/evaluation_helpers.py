"""Synthetic labels/model doubles: never a scientific or human-reviewed benchmark."""
from src.evaluation.dataset import Question, freeze, label_for
from test_answer_chain import FakeGateway
from comparison_helpers import FakeComparisonGateway


class EvaluationGateway:
    def __init__(self):
        self.qa = FakeGateway()
        self.comparison = FakeComparisonGateway()
    @property
    def calls(self): return len(self.qa.prompts) + len(self.comparison.calls)
    def as_runnable(self, *, output_schema):
        return (self.qa if output_schema['title'] == 'AnswerDraft' else self.comparison).as_runnable(output_schema=output_schema)


def prepare_dataset(library, make_pdf, *, comparison=False, unanswerable=False, many=False):
    pages = [' '.join(f'Synthetic attention model experiment {page * 4 + index} reports accuracy 91.2 percent and baseline 86.5 on SyntheticQA.' for index in range(4))
             for page in range(12 if many else 1)]
    papers = [library.ingest(make_pdf(pages, title=f'Evaluation study {number}'),
                             f'evaluation-{number}.pdf').paper for number in range(2)]
    ids = [paper.paper_id for paper in papers] if comparison else [papers[0].paper_id]
    categories = ['methodology', 'results'] if comparison else []
    labels = [label_for(library.catalog.chunks(paper_id)[0], category)
              for paper_id in ids for category in (categories or [None])] if not unanswerable else []
    question = Question(question_id='q1', question='What accuracy was reported?', kind='unanswerable' if unanswerable else ('comparison' if comparison else 'single_paper'),
                        task='comparison' if comparison else 'qa', split='dev', paper_ids=ids, categories=categories,
                        answerable=not unanswerable, expected_points=['Synthetic fixture result.'], rationale='Known generated fixture, not human relevance labels.',
                        required_paper_ids=ids if not unanswerable else [], relevant=labels)
    return freeze(library, [question], name='synthetic-test', synthetic=True)
