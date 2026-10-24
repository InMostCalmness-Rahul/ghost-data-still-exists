"""Multilingual deletion-intent classification.

Determines whether a request_text authorizes deletion.
Returns: 'deletion' | 'not_applicable' | 'ambiguous'
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Intent(Enum):
    DELETION = "deletion"
    NOT_APPLICABLE = "not_applicable"
    AMBIGUOUS = "ambiguous"


# Patterns that indicate a deletion request across languages
DELETION_PATTERNS = [
    # English
    r"\b(delete|remove|erase|close|destroy|eliminate|wipe)\b.*\b(account|profile|data|information|record)\b",
    r"\b(account|profile)\b.*\b(delete|remove|erase|close|destroy)\b",
    r"\b(right to be forgotten|right to erasure|gdpr.*deletion)\b",
    r"\bpermanent(ly)?\s+(delete|remove|erase)\b",
    r"\b(i|please|request)\b.*\b(delete|remove|erase|close)\b",
    r"\b(have|has)\b.*\b(deleted|removed|closed)\b.*\b(account|profile)\b",
    # Spanish
    r"\b(eliminar|borrar|cerrar|suprimir)\b.*\b(cuenta|perfil|datos|informaci[oó]n)\b",
    r"\b(cuenta|perfil)\b.*\b(eliminar|borrar|cerrar)\b",
    # French
    r"\b(supprimer|effacer|fermer|suppression)\b.*\b(compte|profil|donn[ée]es|information)\b",
    r"\b(compte|profil)\b.*\b(supprimer|effacer)\b",
    # German
    r"\b(l[öo]schen|entfernen|schlie[ßs]en|vernichten)\b.*\b(konto|profil|daten|information)\b",
    r"\b(konto|profil)\b.*\b(l[öo]schen|entfernen)\b",
    # Japanese
    r"削除|閉鎖|消去.*(アカウント|プロフィール|データ|情報)",
    r"(アカウント|プロフィール).*削除",
    # Portuguese
    r"\b(excluir|apagar|fechar|remover)\b.*\b(conta|perfil|dados|informa[cç][aã]o)\b",
    r"\b(conta|perfil)\b.*\b(excluir|apagar)\b",
    # Italian
    r"\b(eliminare|cancellare|chiudere|rimuovere)\b.*\b(account|profilo|dati|informazione)\b",
    r"\b(account|profilo)\b.*\b(eliminare|cancellare)\b",
    # Generic: "delete my account" patterns
    r"\bmy\s+(account|profile)\b.*\b(delete|remove|erase|close)\b",
    r"\bdelete\s+my\s+(account|profile)\b",
    # Additional patterns from sample cases
    r"\b(verify|check|audit|confirm)\b.*\b(deletion|deleted)\b",
    r"\btold.*\b(deleted|removed)\b.*but\b.*\b(still|can)\b",
    r"\b(remove|clean|wipe)\b.*\b(personal|data|details)\b",
]

# Patterns that indicate NON-deletion requests (more specific to avoid false positives)
NON_DELETION_PATTERNS = [
    r"\b(right to access|subject access request)\b",
    r"\b(access|export|download|copy|portability)\b.*\b(my|the)\b.*\b(data|information|record)\b",
    r"\b(correct|rectify|update|modify|change)\b.*\b(my|the)\b.*\b(data|information|email|phone)\b",
    r"\b(opt.?out|unsubscribe|stop.*market)\b",
    r"\b(marketing|promotional|newsletter)\b.*\b(opt|stop|unsubscribe)\b",
    r"\b(consent|preference)\b.*\b(withdraw|revoke)\b",
    r"\bhow\s+(to|do\s+I)\b.*\b(delete|remove)\b",  # asking how, not requesting
    r"\bplease\s+tell\s+me\b",
    r"\bwhat\s+is\s+the\s+status\b",
]

COMPILED_DELETION = [re.compile(p, re.IGNORECASE) for p in DELETION_PATTERNS]
COMPILED_NON_DELETION = [re.compile(p, re.IGNORECASE) for p in NON_DELETION_PATTERNS]


@dataclass
class IntentResult:
    intent: Intent
    confidence: float  # 0.0 - 1.0
    matched_patterns: list[str]
    notes: list[str]


def classify_intent(request_text: str) -> IntentResult:
    """Classify whether the request authorizes deletion."""
    if not request_text or not request_text.strip():
        return IntentResult(
            intent=Intent.AMBIGUOUS,
            confidence=0.0,
            matched_patterns=[],
            notes=["empty request text"],
        )

    text = request_text.strip()
    deletion_matches = []
    non_deletion_matches = []

    for pattern in COMPILED_DELETION:
        if pattern.search(text):
            deletion_matches.append(pattern.pattern)

    for pattern in COMPILED_NON_DELETION:
        if pattern.search(text):
            non_deletion_matches.append(pattern.pattern)

    # Decision logic: DEFAULT to DELETION unless clearly non-deletion
    # Only NOT_APPLICABLE for explicit access/export/correction/opt-out requests
    if non_deletion_matches and not deletion_matches:
        return IntentResult(
            intent=Intent.NOT_APPLICABLE,
            confidence=0.9,
            matched_patterns=non_deletion_matches,
            notes=["non-deletion intent detected"],
        )

    # If any deletion pattern matches, treat as deletion (even if ambiguous patterns also match)
    if deletion_matches:
        return IntentResult(
            intent=Intent.DELETION,
            confidence=0.85 if not non_deletion_matches else 0.7,
            matched_patterns=deletion_matches,
            notes=["deletion intent detected"] + (["ambiguous signals also present"] if non_deletion_matches else []),
        )

    # Ambiguous or unsupported text does not authorize a deletion audit.
    return IntentResult(
        intent=Intent.AMBIGUOUS,
        confidence=0.0,
        matched_patterns=[],
        notes=["no clear authorization for deletion"],
    )


def is_deletion_authorized(request_text: str) -> tuple[bool, IntentResult]:
    """Convenience: returns (authorized, full_result)."""
    result = classify_intent(request_text)
    return result.intent == Intent.DELETION, result