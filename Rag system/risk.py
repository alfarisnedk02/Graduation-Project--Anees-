# risk.py
from dataclasses import dataclass
from typing import Dict, List, Optional
import re
import uuid

@dataclass
class RiskResult:
    risk_level: str            # none | emergency
    action: str                # continue | stop_and_refer
    matched: List[str]
    referral: Dict[str, str]

class CriticalRiskDetector:
    """
    Minimal, reliable crisis detector.
    - Matches suicide/self-harm phrases INCLUDING common misspellings like 'sucide'
    - If triggered -> stop immediately and show Jordan referral numbers
    """

    # Match correct + misspellings
    _CRISIS_REGEX = [
        r"\bkill\s*my\s*self\b",
        r"\bend\s*my\s*life\b",
        r"\bhurt\s*my\s*self\b",
        r"\bself[-\s]*harm\b",
        r"\bsuicid(?:e|al|ality)?\b",   # suicide / suicidal / suicidality
        r"\bsucide\b",                 # misspelling
        r"\bsuicde\b",                 # misspelling
        r"\bi\s*(want|wanna|am\s*going)\s*to\s*(?:die|suicid(?:e|al)|sucide)\b",
    ]

    _JORDAN_REFERRAL = {
        "Emergency (Police)": "911",
        "Ambulance": "193",
        "Fire Department": "199",
        "MOH Crisis Unit (Amman)": "+962 5 057 921",
        "IMC/MoH Mental Health Hotline 24/7":"+962 795 785 095",
        "JCPA Hotline provides 24/7": "+962795440416",
        "24/7 Mental Health & Psychosocial Support Hotline": "+962 79 578 5095",
        "Guidance": (
            "If you feel in immediate danger, call emergency services now. "
            "If you can, reach out to a trusted and supportive friend nearby."
        )
    }

    def __init__(self, referral: Optional[Dict[str, str]] = None):
        self.referral = referral or dict(self._JORDAN_REFERRAL)

    def new_session_id(self) -> str:
        return f"sess_{uuid.uuid4().hex}"

    def decide(self, text: str, rag_client=None, session_id: Optional[str] = None) -> RiskResult:
        t = (text or "").lower().strip()
        matched = [rx for rx in self._CRISIS_REGEX if re.search(rx, t, flags=re.IGNORECASE)]

        if matched:
            return RiskResult(
                risk_level="emergency",
                action="stop_and_refer",
                matched=matched,
                referral=self.referral,
            )

        return RiskResult(
            risk_level="none",
            action="continue",
            matched=[],
            referral=self.referral,
        )

    def format_referral_message(self, result: RiskResult) -> str:
        return "\n".join([
            "I’m really sorry you’re feeling this way. I’m concerned about your safety.",
            "I can’t continue with questions right now. Please get support immediately.",
            "",
            "Jordan support:",
            f"- Emergency (Police): {result.referral.get('Emergency (Police)','')}",
            f"- Ambulance: {result.referral.get('Ambulance','')}",
            f"- Fire Department: {result.referral.get('Fire Department','')}",
            f"- MOH Crisis Unit (Amman): {result.referral.get('MOH Crisis Unit (Amman)','')}",
            f"- IMC/MoH Mental Health Hotline 24/7: {result.referral.get('IMC/MoH Mental Health Hotline 24/7','')}",
            f"- JCPA Hotline provides 24/7: {result.referral.get('JCPA Hotline provides 24/7','')}",
            f"- 24/7 Mental Health & Psychosocial Support Hotline: {result.referral.get('24/7 Mental Health & Psychosocial Support Hotline','')}",

            "",
            result.referral.get("Guidance",""),
        ])
