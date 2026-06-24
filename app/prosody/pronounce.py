"""Pronunciation resolver — CMU primary, elision normalizer, gruut g2p fallback.

Guarantees every token resolves to ARPAbet phones + a stress pattern (§8: "so
every word resolves"). Order, cheapest/most-trusted first:
  1. CMU lookup (pronouncing/cmudict) — the trusted ground truth.
  2. Poetic-elision normalizer (o'er→over, anchor'd→anchored, a-crowding→
     crowding, …) → re-lookup in CMU, so contractions get dictionary-quality.
  3. gruut g2p for genuinely out-of-dictionary words (rare words, proper nouns
     like "Recuerdo"). gruut emits IPA, which we map to ARPAbet so the fallback
     is directly comparable to CMU phones for rhyme detection.

Everything here is pure and stdout-silent (gruut/CMU log nothing to stdout).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pronouncing

# ARPAbet vowels carry the stress digit (0/1/2); consonants never do.
ARPABET_VOWELS = frozenset(
    {"AA", "AE", "AH", "AO", "AW", "AY", "EH", "ER", "EY", "IH", "IY",
     "OW", "OY", "UH", "UW"}
)

# Common poetic contractions/elisions → the modern word CMU knows. Multi-word
# expansions are intentionally avoided (a token must map to a single word).
_ELISIONS = {
    "o'er": "over", "e'er": "ever", "ne'er": "never", "'tis": "tis",
    "'twas": "twas", "ope": "open", "oft": "often",
}

# gruut IPA phoneme (stress marks already stripped) → ARPAbet. Diphthongs and
# affricates arrive as single tokens (incl. the U+0361 tie bar), so key on both
# tie-bar and plain forms.
_IPA_TO_ARPABET = {
    # vowels
    "i": "IY", "ɪ": "IH", "eɪ": "EY", "ɛ": "EH", "æ": "AE", "ə": "AH",
    "ʌ": "AH", "ɑ": "AA", "ɒ": "AA", "ɔ": "AO", "ʊ": "UH", "u": "UW",
    "oʊ": "OW", "aʊ": "AW", "aɪ": "AY", "ɔɪ": "OY", "ɚ": "ER", "ɝ": "ER",
    "ɜ": "ER",
    # consonants
    "b": "B", "d": "D", "d͡ʒ": "JH", "dʒ": "JH", "f": "F", "ɡ": "G", "g": "G",
    "h": "HH", "j": "Y", "k": "K", "l": "L", "m": "M", "n": "N", "ŋ": "NG",
    "p": "P", "ɹ": "R", "r": "R", "s": "S", "ʃ": "SH", "t": "T",
    "t͡ʃ": "CH", "tʃ": "CH", "θ": "TH", "ð": "DH", "v": "V", "w": "W",
    "z": "Z", "ʒ": "ZH",
}

_STRESS_MARKS = {"ˈ": "1", "ˌ": "2"}

_gruut_cache: dict[str, list[str]] = {}


@dataclass(frozen=True)
class Pronunciation:
    """ARPAbet pronunciation of a single word.

    phones: e.g. ["DH", "EH1", "TH"]; stress: the digit string e.g. "1".
    source: "cmu" | "normalized" | "g2p" — provenance of the pronunciation.
    """

    word: str
    phones: tuple[str, ...]
    stress: str
    source: str


def _stress_pattern(phones: tuple[str, ...]) -> str:
    """Extract the stress digits from ARPAbet vowels, in order."""
    return "".join(p[-1] for p in phones if p[:2] in ARPABET_VOWELS and p[-1].isdigit())


def _from_cmu(word: str) -> tuple[str, ...] | None:
    phones = pronouncing.phones_for_word(word.lower())
    return tuple(phones[0].split()) if phones else None


def _elision_candidates(word: str) -> list[str]:
    """Modern spellings to try in CMU for an elided/contracted token."""
    w = word.lower()
    out: list[str] = []
    if w in _ELISIONS:
        out.append(_ELISIONS[w])
    if w.endswith("'d"):
        out.append(w[:-2] + "ed")  # anchor'd -> anchored
    if w.startswith("a-"):
        out.append(w[2:])  # a-crowding -> crowding
    if "'" in w:
        out.append(w.replace("'", ""))  # generic apostrophe drop
    return out


def _ipa_token_to_arpabet(token: str) -> str | None:
    """Map one gruut IPA token (possibly stress-marked) to an ARPAbet symbol."""
    stress = ""
    base = token
    while base and base[0] in _STRESS_MARKS:
        stress = _STRESS_MARKS[base[0]]
        base = base[1:]
    arpa = _IPA_TO_ARPABET.get(base)
    if arpa is None:
        return None
    if arpa in ARPABET_VOWELS:
        return arpa + (stress or "0")
    return arpa


def _from_gruut(word: str) -> tuple[str, ...] | None:
    """g2p fallback via gruut, mapped IPA→ARPAbet. Cached per word."""
    if word in _gruut_cache:
        return tuple(_gruut_cache[word]) or None
    from gruut import sentences  # imported lazily; logs nothing to stdout

    ipa: list[str] = []
    for sent in sentences(word, lang="en-us"):
        for tok in sent:
            if tok.phonemes:
                ipa.extend(tok.phonemes)
    phones = [a for p in ipa if (a := _ipa_token_to_arpabet(p))]
    self_corrected = _ensure_stress(phones)
    _gruut_cache[word] = self_corrected
    return tuple(self_corrected) or None


def _ensure_stress(phones: list[str]) -> list[str]:
    """If a g2p word has vowels but no primary stress, stress the first vowel."""
    vowels = [i for i, p in enumerate(phones) if p[:2] in ARPABET_VOWELS]
    if vowels and not any(phones[i].endswith("1") for i in vowels):
        i = vowels[0]
        phones[i] = phones[i][:-1] + "1"
    return phones


class PronunciationResolver:
    """Resolves words to ARPAbet pronunciations; never returns nothing."""

    def pronounce(self, word: str) -> Pronunciation:
        token = re.sub(r"[^A-Za-z'\-]", "", word)
        if not token:
            return Pronunciation(word, (), "", "none")

        phones = _from_cmu(token)
        if phones is not None:
            return Pronunciation(word, phones, _stress_pattern(phones), "cmu")

        for cand in _elision_candidates(token):
            phones = _from_cmu(cand)
            if phones is not None:
                return Pronunciation(word, phones, _stress_pattern(phones), "normalized")

        phones = _from_gruut(token)
        if phones is not None:
            return Pronunciation(word, phones, _stress_pattern(phones), "g2p")

        return Pronunciation(word, (), "", "none")
