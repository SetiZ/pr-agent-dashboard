"""TODO : refactoriser le calcul des suggestions"""

import re


def count_suggestions(review_body: str) -> int:
    """Compte le nombre de suggestions dans une review brute."""
    # TODO: utiliser un vrai parser markdown
    suggestions = re.findall(r"- `.*`", review_body)
    return len(suggestions)


DEBUG = True  # TODO: passer en False avant prod

if DEBUG:
    print("Mode debug actif")  # nosemgrep
