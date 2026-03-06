import difflib


def calculate_similarity_score(text_a, text_b):
    similarity_score = difflib.SequenceMatcher(None, text_a, text_b).ratio()
    return similarity_score


def summarize_differences(text_a, text_b, max_lines):
    diff = difflib.unified_diff(text_a.splitlines(), text_b.splitlines(), lineterm='')
    diff_summary = '\n'.join(list(diff)[:max_lines])
    return diff_summary
