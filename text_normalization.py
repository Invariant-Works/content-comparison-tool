import re
from html import unescape

IGNORE_CASE = True


def normalize_text(text, ignore_case=None):
    if ignore_case is None:
        ignore_case = IGNORE_CASE
    text = unescape(text)
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    if ignore_case:
        text = text.lower()
    return text
