"""Deterministic metrics with explicit denominators, exclusions and rank limits."""
import statistics


def ranked_metrics(ranked_ids, relevant_ids, *, k):
    if isinstance(k, bool) or not isinstance(k, int) or k <= 0:
        raise ValueError("K must be a positive integer")
    # Duplicate results cannot earn extra credit or push a relevant result back.
    ranked = list(dict.fromkeys(ranked_ids))[:k]
    relevant = set(relevant_ids)
    if not relevant:
        return {"precision": None, "recall": None, "reciprocal_rank": None, "hits": 0, "relevant_count": 0}
    hits = len(set(ranked) & relevant)
    first = next((index for index, item in enumerate(ranked, 1) if item in relevant), None)
    return {"precision": hits / k, "recall": hits / len(relevant),
            "reciprocal_rank": 1 / first if first else 0.0, "hits": hits, "relevant_count": len(relevant)}


def context_metrics(chunks, relevant_ids, required_paper_ids):
    by_id = {chunk.chunk_id: chunk for chunk in chunks}
    relevant = set(relevant_ids)
    required = set(required_paper_ids)
    hits = set(by_id) & relevant
    return {"precision": len(hits) / len(by_id) if by_id and relevant else (0.0 if relevant else None),
            "recall": len(hits) / len(relevant) if relevant else None,
            "paper_coverage": len({by_id[key].paper_id for key in hits} & required) / len(required) if required else None,
            "selected_count": len(by_id), "hits": len(hits)}


def describe(values):
    values = [value for value in values if value is not None]
    return {"count": len(values), "mean": statistics.mean(values) if values else None,
            "median": statistics.median(values) if values else None,
            "minimum": min(values) if values else None, "maximum": max(values) if values else None}
