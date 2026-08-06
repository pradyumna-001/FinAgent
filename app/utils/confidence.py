def confidence_flag(score: float, *, threshold: float = 0.75) -> bool:
    return score <= threshold
