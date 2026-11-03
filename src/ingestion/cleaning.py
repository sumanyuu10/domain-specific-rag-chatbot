"""Conservative cleanup: preserve numbers, technical punctuation, and paragraphs."""
import re


def clean_text(text: str) -> str:
    text = text.replace("\x00", "").replace("\u00ad", "")
    for source, target in {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff"}.items():
        text = text.replace(source, target)
    lines = [re.sub(r"[^\S\n]+", " ", line).strip() for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def clean_pages(texts: list[str]) -> list[str]:
    """Remove only repeated short edge lines, never interior experimental text."""
    cleaned = [clean_text(text) for text in texts]
    edge_counts = {}
    for text in cleaned:
        lines = text.splitlines()
        edges = {lines[0], lines[-1]} if lines else set()
        for line in edges:
            if 3 <= len(line) <= 100 and not any(char.isdigit() for char in line):
                edge_counts[line] = edge_counts.get(line, 0) + 1
    repeated = {line for line, count in edge_counts.items() if count >= max(3, len(texts) * 0.6)}
    result = []
    for number, text in enumerate(cleaned, 1):
        lines = text.splitlines()
        while lines and (lines[0] in repeated or lines[0] == str(number)):
            lines.pop(0)
        while lines and (lines[-1] in repeated or lines[-1] == str(number)):
            lines.pop()
        result.append("\n".join(lines).strip())
    return result
