"""
Entity Similarity / Duplicate Detection using sentence-transformers.
Improves on Layer 2's Levenshtein-based fuzzy deduplication.
"""
import logging
import os
import pickle
import tempfile
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

MODEL_NAME = "entity_similarity"
EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def build_entity_text(props: dict) -> str:
    """Concatenates fields most useful for name-based entity matching."""
    parts = [
        str(props.get("name", "")),
        str(props.get("cin", props.get("din", ""))),
        str(props.get("registeredAddress", props.get("address", ""))),
    ]
    return " | ".join(p for p in parts if p.strip())


async def compute_similarity(text_a: str, text_b: str) -> float:
    """Returns cosine similarity between two entity text representations."""
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np
        model = _get_embed_model()
        embs = model.encode([text_a, text_b], normalize_embeddings=True)
        return float(np.dot(embs[0], embs[1]))
    except ImportError:
        from rapidfuzz import fuzz
        return fuzz.token_sort_ratio(text_a, text_b) / 100.0


_embed_model_instance = None


def _get_embed_model():
    global _embed_model_instance
    if _embed_model_instance is None:
        from sentence_transformers import SentenceTransformer
        _embed_model_instance = SentenceTransformer(EMBED_MODEL)
    return _embed_model_instance


async def train_threshold(
    known_pairs: list[dict],  # each: {text_a, text_b, is_duplicate: bool}
    artifact_dir: Optional[str] = None,
) -> dict:
    """Finds optimal similarity threshold using labeled duplicate pairs."""
    from models.registry import model_registry

    if not known_pairs:
        return {"status": "skipped", "reason": "no_labeled_pairs"}

    sims, labels = [], []
    for pair in known_pairs:
        sim = await compute_similarity(pair["text_a"], pair["text_b"])
        sims.append(sim)
        labels.append(1 if pair["is_duplicate"] else 0)

    try:
        import numpy as np
        from sklearn.metrics import f1_score

        sims_np = np.array(sims)
        labels_np = np.array(labels)
        best_thresh, best_f1 = 0.85, 0.0
        for t in np.arange(0.70, 0.99, 0.01):
            preds = (sims_np >= t).astype(int)
            f1 = f1_score(labels_np, preds, zero_division=0)
            if f1 > best_f1:
                best_f1, best_thresh = f1, float(t)

        artifact = {"threshold": best_thresh, "embed_model": EMBED_MODEL}
        version = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        if artifact_dir is None:
            artifact_dir = tempfile.gettempdir()
        artifact_path = os.path.join(artifact_dir, f"{MODEL_NAME}_{version}.pkl")
        with open(artifact_path, "wb") as f:
            pickle.dump(artifact, f)

        metrics = {"f1": best_f1, "threshold": best_thresh, "n_pairs": len(known_pairs)}
        model_id = await model_registry.register(
            model_name=MODEL_NAME,
            model_type="SentenceTransformer+threshold",
            version=version,
            evaluation_metrics=metrics,
            artifact_path=artifact_path,
            training_sample_size=len(known_pairs),
            status="champion",
        )
        await model_registry.promote_to_champion(model_id, MODEL_NAME)
        return {"model_id": model_id, "metrics": metrics}

    except ImportError:
        return {"status": "skipped", "reason": "sentence_transformers_not_installed"}
