"""One lazy local Sentence Transformers model, wrapped by LlamaIndex."""
from functools import cached_property

from src.config import IngestionSettings
from src.schemas import IngestionError


class LocalEmbeddings:
    def __init__(self, settings: IngestionSettings):
        self.settings = settings

    @cached_property
    def model(self):
        try:
            from llama_index.embeddings.huggingface import HuggingFaceEmbedding
            return HuggingFaceEmbedding(
                model_name=self.settings.embedding_model,
                revision=self.settings.embedding_revision,
                cache_folder=str(self.settings.data_dir / "models"),
                device="cpu", normalize=True, max_length=self.settings.embedding_max_tokens,
                trust_remote_code=False,
            )
        except Exception as error:
            raise IngestionError(
                "The local MiniLM model could not load. First use needs internet access "
                "to download the pinned public model; previously indexed papers remain saved."
            ) from error

    def tokenize(self, text: str, *, special_tokens=False):
        # Bound to the pinned HuggingFaceEmbedding integration; tested with its
        # actual SentenceTransformer tokenizer, not LlamaIndex's default tokenizer.
        return self.model._model.tokenizer.encode(text, add_special_tokens=special_tokens)
