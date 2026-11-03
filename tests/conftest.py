"""Synthetic PDFs and deterministic embeddings; no credentials or private papers."""
import hashlib
import math
import re

from llama_index.core.base.embeddings.base import BaseEmbedding
from pydantic import PrivateAttr
import pymupdf
import pytest

from src.config import IngestionSettings
from src.ingestion.pipeline import PaperLibrary


def pytest_addoption(parser):
    parser.addoption("--run-embedding-integration", action="store_true", help="Download/use the pinned public MiniLM model on CPU (no LLM calls).")


def pytest_configure(config):
    config.addinivalue_line("markers", "embedding_integration: actual local MiniLM integration; explicit opt-in")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-embedding-integration"):
        for item in items:
            if "embedding_integration" in item.keywords:
                item.add_marker(pytest.mark.skip(reason="Pass --run-embedding-integration to use the actual MiniLM model."))


class CountingEmbedding(BaseEmbedding):
    _calls: int = PrivateAttr(default=0)

    def _get_text_embedding(self, text):
        self._calls += 1
        values = list(hashlib.sha256(text.encode()).digest()) * 12
        norm = math.sqrt(sum(value * value for value in values))
        return [value / norm for value in values]

    def _get_query_embedding(self, query):
        return self._get_text_embedding(query)

    async def _aget_query_embedding(self, query):
        return self._get_query_embedding(query)


class FakeEmbeddings:
    def __init__(self):
        self.model = CountingEmbedding(model_name="test-only")

    def tokenize(self, text, *, special_tokens=False):
        return re.findall(r"\w+|[^\w\s]", text) + (["[CLS]", "[SEP]"] if special_tokens else [])


class NoEmbeddings:
    @property
    def model(self):
        raise AssertionError("Restart/duplicate/delete must not load or call the model")

    def tokenize(self, *args, **kwargs):
        raise AssertionError("Restart must not rechunk existing papers")


@pytest.fixture
def make_pdf():
    def create(texts=None, *, title="Synthetic machine learning study", password=None):
        document = pymupdf.open()
        for text in texts if texts is not None else [
            "Our transformer model uses attention for language understanding. "
            "Experiments on the SyntheticQA dataset achieve accuracy of 91.2 percent. "
            "The baseline achieves 86.5 percent. Limitations include a small training dataset."
        ]:
            page = document.new_page()
            page.insert_textbox(pymupdf.Rect(60, 60, 530, 780), text, fontsize=10)
        document.set_metadata({"title": title})
        options = {"encryption": pymupdf.PDF_ENCRYPT_AES_256, "owner_pw": password, "user_pw": password} if password else {}
        payload = document.tobytes(**options)
        document.close()
        return payload
    return create


@pytest.fixture
def settings(tmp_path):
    return IngestionSettings(data_dir=tmp_path / "data")


@pytest.fixture
def embeddings():
    return FakeEmbeddings()


@pytest.fixture
def library(settings, embeddings):
    service = PaperLibrary(settings, embeddings=embeddings)
    yield service
    service.close()
