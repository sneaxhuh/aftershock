"""Real text embeddings, cached in the workspace graph; never invented vectors."""

import hashlib
import math
import os
from google import genai
from google.genai import types

DIMENSIONS = 768


class Embeddings:
    def __init__(self, store):
        self.store = store
        self.model = os.environ.get("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
        self.enabled = (
            bool(os.environ.get("GEMINI_API_KEY"))
            and os.environ.get("AGENT_MODE", "live") == "live"
            and os.environ.get("EMBEDDINGS_ENABLED", "true").lower() == "true"
        )
        self.error = None

    def encode(self, text, purpose="RETRIEVAL_DOCUMENT"):
        if not self.enabled:
            self.error = "Embeddings disabled or no live model key; full-text retrieval remains available."
            return None
        text = text[:6000]
        key = hashlib.sha256(f"{self.model}:{purpose}:{text}".encode()).hexdigest()
        rows = self.store.q(
            "MATCH (e:EmbeddingCache {id:$id}) RETURN e.values", {"id": key}
        )
        if rows:
            return rows[0][0]
        client = genai.Client(
            api_key=os.environ["GEMINI_API_KEY"],
            http_options=types.HttpOptions(
                timeout=15000, retry_options=types.HttpRetryOptions(attempts=1)
            ),
        )
        try:
            config = types.EmbedContentConfig(output_dimensionality=DIMENSIONS)
            if self.model == "gemini-embedding-001":
                config.task_type = purpose
            response = client.models.embed_content(
                model=self.model, contents=text, config=config
            )
            values = response.embeddings[0].values
            if len(values) != DIMENSIONS or not all(math.isfinite(v) for v in values):
                raise ValueError("Unexpected embedding dimensions")
            norm = math.sqrt(sum(v * v for v in values))
            if not norm:
                raise ValueError("Empty embedding")
            values = [v / norm for v in values]
            self.store.q(
                "MERGE (e:EmbeddingCache {id:$id}) SET e.values=$values,e.model=$model",
                {"id": key, "values": values, "model": self.model},
            )
            return values
        except Exception as error:
            from redis.exceptions import RedisError

            if isinstance(error, RedisError):
                raise
            self.error = f"Embedding provider unavailable ({type(error).__name__}); using explicit full-text retrieval."
            self.enabled = False
            return None
        finally:
            client.close()

    def index(self, graph, label, id_, text):
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        rows = self.store.q(
            f"MATCH (n:{label} {{id:$id}}) RETURN n.embedding_model,n.embedding_text_hash",
            {"id": id_},
            graph,
        )
        if rows and rows[0] == [self.model, text_hash]:
            return True
        vector = self.encode(text)
        if vector is None:
            return False
        self.store.q(
            f"MATCH (n:{label} {{id:$id}}) SET n.embedding=vecf32($values),n.embedding_model=$model,n.embedding_text_hash=$hash",
            {"id": id_, "values": vector, "model": self.model, "hash": text_hash},
            graph,
        )
        return True
