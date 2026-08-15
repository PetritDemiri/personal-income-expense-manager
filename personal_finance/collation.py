"""Renditja alfabetike shqipe / Albanian collation.

Sorting Albanian text by Unicode code point is wrong twice over. Accented
letters land past Z, so "Ëmbëlsira" sorts after "Zarf". And nine of the
alphabet's 36 letters are digraphs - dh, gj, ll, nj, rr, sh, th, xh, zh - each
a letter in its own right that follows its base letter. In Albanian, every word
beginning with S comes before every word beginning with Sh; treating "sh" as
two characters interleaves them instead.

The alphabet, in order:

    a b c ç d dh e ë f g gj h i j k l ll m n nj o p q r rr s sh t th u v x xh
    y z zh

Text is tokenised into letters - digraphs matched first, so "shi" is [sh, i]
rather than [s, h, i] - and each token is ranked by its place in that alphabet.

Latin letters absent from Albanian are placed where a reader would expect
rather than dumped at the end: only w is missing from the basic Latin set, and
it goes between v and x. The relative order of every shared letter is the same
in both alphabets, so English category names sort correctly too.
"""

import unicodedata

# The Albanian alphabet in collation order.
ALPHABET = [
    "a",
    "b",
    "c",
    "ç",
    "d",
    "dh",
    "e",
    "ë",
    "f",
    "g",
    "gj",
    "h",
    "i",
    "j",
    "k",
    "l",
    "ll",
    "m",
    "n",
    "nj",
    "o",
    "p",
    "q",
    "r",
    "rr",
    "s",
    "sh",
    "t",
    "th",
    "u",
    "v",
    "x",
    "xh",
    "y",
    "z",
    "zh",
]

# The nine two-character letters, matched before single characters.
DIGRAPHS = frozenset(letter for letter in ALPHABET if len(letter) == 2)

# Ranks are spaced out so a letter can be slotted between two others.
LETTER_RANK = {letter: (index + 1) * 10 for index, letter in enumerate(ALPHABET)}

# Latin letters that are not Albanian letters, given the position a reader
# would expect rather than being pushed past the end of the alphabet.
FOREIGN_RANK = {"w": LETTER_RANK["v"] + 5}

# Token groups, compared before rank within a group. Punctuation and spaces
# sort before digits, digits before letters.
GROUP_SYMBOL = 0
GROUP_DIGIT = 1
GROUP_LETTER = 2
GROUP_OTHER = 3


def tokenize(text):
    """Split text into Albanian letters, matching digraphs as single letters.

    >>> tokenize("Shqiperia")
    ['sh', 'q', 'i', 'p', 'e', 'r', 'i', 'a']

    Matching is greedy and left to right, which is how Albanian dictionaries
    treat these sequences. The rare compound where a digraph spans a morpheme
    boundary is collated as the digraph; that matches published practice.

    Runs of digits are kept together so they can be compared as numbers rather
    than character by character, which would put "10" before "9".
    """
    # Compose accents first, so a decomposed "e + combining diaeresis" is
    # recognised as ë rather than as two tokens.
    text = unicodedata.normalize("NFC", text).casefold()

    tokens = []
    index = 0
    while index < len(text):
        if text[index].isdigit():
            start = index
            while index < len(text) and text[index].isdigit():
                index += 1
            tokens.append(text[start:index])
            continue

        pair = text[index : index + 2]
        if pair in DIGRAPHS:
            tokens.append(pair)
            index += 2
        else:
            tokens.append(text[index])
            index += 1
    return tokens


def token_rank(token):
    """Sort rank for one token: (group, position, raw)."""
    if token in LETTER_RANK:
        return (GROUP_LETTER, LETTER_RANK[token], "")
    if token in FOREIGN_RANK:
        return (GROUP_LETTER, FOREIGN_RANK[token], "")
    if token.isdigit():
        return (GROUP_DIGIT, int(token), "")
    if token.isalpha():
        # A letter from some other script. Ordered after the alphabet, and
        # consistently among themselves.
        return (GROUP_OTHER, 0, token)
    return (GROUP_SYMBOL, 0, token)


def sort_key(name):
    """Key for sorting a name in Albanian alphabetical order.

    Case-insensitive. The raw name is kept as a final tiebreaker so names that
    collate identically still have a stable, repeatable order.
    """
    return ([token_rank(token) for token in tokenize(name)], name)


def sort_names(names):
    """Return names sorted in Albanian alphabetical order."""
    return sorted(names, key=sort_key)
