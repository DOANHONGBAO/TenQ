"""Deterministic judge rules that run before any AI call (hybrid evaluation steps 2 and 3).

They are deliberately conservative: a rule fires only on unambiguous patterns, and every
other question goes to the model. Pure functions, no I/O.
"""

import re

from app.models.game import Answer
from app.models.question import Question

# Open-ended questions (OQ-01): cannot be answered with yes or no.
_OPEN_ENDED = re.compile(r"^(what|who|whom|whose|where|when|why|how|which)\b")
_OPEN_ENDED_REQUEST = re.compile(r"^(tell|give|show|name|list|describe|explain|spell|say)\b")

# Attempts to manipulate the judge or extract hidden information (OQ-01).
_MANIPULATION = re.compile(
    r"\b("
    r"ignore (all |any |the )?(previous|prior|above|earlier) (instructions?|rules?|prompts?)"
    r"|(system|hidden|initial) (prompt|message|instructions?)"
    r"|your (instructions?|rules?|prompt|configuration)"
    r"|(print|repeat|reveal|show|output|leak|dump|display) (me )?"
    r"(everything|all of|the (prompt|instructions|rules|word|answer|secret|text above)"
    r"|your (prompt|instructions|rules|configuration))"
    r"|(return|answer|respond|reply|output|say) (with )?(win|yes|no|irrelevant|penalty)\b"
    r"|regardless of"
    r"|base ?64|rot ?13|hex(adecimal)? encod|encod(e|ed|ing) (it|the)"
    r"|you are now|act as|pretend (to be|you)|developer mode|jailbreak"
    r"|(the )?secret word is\b(?! [a-z]+\?$)"
    r"|tell me the (secret|answer|word)"
    r")"
)

# Questions about the word's spelling instead of the thing it names (OQ-09): letters, length,
# alphabetical order, sounds, grammar. They let players find the word by search, not deduction.
_WORD_FORM = re.compile(
    r"\b("
    r"letters?|spell(s|ed|ing)?|vowels?|consonants?|syllables?|rhym(e|es|ing)"
    r"|alphabet(ical(ly)?)?|dictionary|initials?|acronym|abbreviat\w*|anagram|palindrome"
    r"|nouns?|verbs?|adjectives?|adverbs?|part of speech|plural|singular|compound word"
    r")\b"
    r"|\b\d+ characters?\b"
    # "Does it start with S?", "Does it end in an e?", "Does it contain t?" (letter at the end,
    # so "Does it start with a bang?" is not caught)
    r"|\b(start|starts|begin|begins|end|ends|contain|contains|include|includes)"
    r" (with |in )?(an? |the )?[a-z]$"
    # "Is there an e in it?"
    r"|\bis there (an? )?[a-z] in (it|the word)$"
)

# One property per question (OQ-01): "Is it red and big?", "Is it a cat or a dog?", lists.
_COMPOUND = re.compile(r",|;|&|/|\+|\b(and|or|nor|but|either|neither|both|also|as well as|plus)\b")


def prefilter(question: Question) -> Answer | None:
    """PENALTY for inputs that are clearly not a genuine yes/no question; else None."""
    text = question.normalized
    if text.count("?") > 0:  # normalized text drops only the trailing "?"; any left = 2+ questions
        return Answer.PENALTY
    if _MANIPULATION.search(text):
        return Answer.PENALTY
    if _OPEN_ENDED.match(text) or _OPEN_ENDED_REQUEST.match(text):
        return Answer.PENALTY
    if _WORD_FORM.search(text) or _COMPOUND.search(text):
        return Answer.PENALTY
    return None


_ARTICLE = r"(?:a |an |the |some )?"
_GUESS_FORMS = tuple(
    re.compile(form.replace("{a}", _ARTICLE).replace("{w}", r"(?P<w>[a-z]+)"))
    for form in (
        r"is it {a}{w}",
        r"is (?:it|this|that) (?:called )?{a}{w}",
        r"is the (?:secret )?(?:word|answer|thing|object) {a}{w}",
        r"(?:is|could|might) the (?:secret )?(?:word|answer) be {a}{w}",
        r"(?:the )?(?:secret )?(?:word|answer) is {a}{w}",
        r"(?:are they|are these) {w}",
    )
)
# Only the explicit "the (secret) word/answer is X" phrasing names a candidate word for sure.
# "Is it red?" has the same shape as "Is it an apple?" but asks about a property.
_EXPLICIT_GUESS = tuple(
    re.compile(form.replace("{a}", _ARTICLE).replace("{w}", r"(?P<w>[a-z]+)"))
    for form in (
        r"is the (?:secret )?(?:word|answer) {a}{w}",
        r"(?:is|could|might) the (?:secret )?(?:word|answer) be {a}{w}",
        r"(?:the )?(?:secret )?(?:word|answer) is {a}{w}",
    )
)


def _plural_forms(word: str) -> set[str]:
    return {word, word + "s", word + "es"}


def exact_guess(question: Question, word: str) -> bool:
    """True when the whole question is a direct guess of the word (or a simple plural).

    "Is it an apple?" is a guess; "Is it bigger than an apple?" is not, so it goes to the model.
    """
    for form in _GUESS_FORMS:
        match = form.fullmatch(question.normalized)
        if match and match.group("w") in _plural_forms(word):
            return True
    return False


def wrong_explicit_guess(question: Question, word: str) -> bool:
    """True for "Is the secret word X?" when X is not the word: the answer is NO, no AI call."""
    for form in _EXPLICIT_GUESS:
        match = form.fullmatch(question.normalized)
        if match and match.group("w") not in _plural_forms(word):
            return True
    return False
