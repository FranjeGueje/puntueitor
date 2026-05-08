import re
from difflib import SequenceMatcher

def normalize_title(title: str) -> str:
    NORMALIZATION_PATTERNS = [
        re.compile(r'\(.*?\)'),
        re.compile(r'\[.*?\]'),
        re.compile(r'[:\-–]'),
    ]

    REMOVE_WORDS = (
        'remastered', 'definitive', 'goty', 'complete', 'deluxe edition',
        'edition', 'enhanced', 'collection', 'bundle', 'pack'
    )
    title = title.lower()

    for p in NORMALIZATION_PATTERNS:
        title = p.sub(' ', title)

    for w in REMOVE_WORDS:
        title = re.sub(rf'\b{w}\b', ' ', title)

    title = re.sub(r'\s+', ' ', title)
    return title.strip()

def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio() 
