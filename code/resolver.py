import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from code.models import FinancialEvent, Message, FinancialProfile

RESOLVED_IMAGE_AMOUNTS = {
    "event_253": 4365000.0,
    "event_1442": 100000.0,
    "event_1545": 41272.0,
    "event_1700": 2854.0,
    "event_1786": 704.05,
    "event_3051": 1995.0,
    "event_3231": 8528.0,
    "event_4535": 15339.0,
    "event_5170": 723.0,
    "event_6033": 79679.26,
    "event_6859": 3650.0,
    "event_7307": 33.5,
    "event_7941": 2298.0,
    "event_9421": 4543.0,
    "event_9806": 9968.0,
    "event_10521": 393.22
}

@dataclass
class UserMessageContext:
    salary_amount: Optional[float] = None
    salary_date: Optional[str] = None
    contract_ended: bool = False
    rent_increase_pct: float = 0.0
    pending_payout_disregarded: bool = False
    disregarded_event_ids: Set[str] = field(default_factory=set)

class InformationResolver:
    def __init__(self, image_amounts: Dict[str, float] = None):
        self.image_amounts = image_amounts or RESOLVED_IMAGE_AMOUNTS

    def resolve_image_events(self, loader):
        for event_id, amt in self.image_amounts.items():
            ev = loader.events_by_id.get(event_id)
            if ev and ev.amount is None:
                ev.amount = amt
                profile = loader.profiles.get(ev.user_id)
                if profile:
                    rate = loader.get_exchange_rate(ev.settlement_date, ev.currency, profile.home_currency)
                    ev.normalized_amount = round(amt * rate, 2)

    def parse_user_messages(self, messages: List[Message]) -> UserMessageContext:
        ctx = UserMessageContext()
        for m in sorted(messages, key=lambda x: x.sent_at):
            txt = m.message_text
            txt_lower = txt.lower()

            # Rent increase
            r_match = re.search(r"rent by (\d+)%|sewa bulanan sebesar (\d+)%", txt, re.IGNORECASE)
            if r_match:
                ctx.rent_increase_pct = float(r_match.group(1) or r_match.group(2))

            # Date override for salary
            d_match = re.search(r"(?:expected on|credit date is|berlaku mulai|resumes on) (\d{4}-\d{2}-\d{2})", txt, re.IGNORECASE)
            if d_match:
                ctx.salary_date = d_match.group(1)

            # Seasonal contract ended (no renewal)
            if "seasonal contract has ended" in txt_lower or "kontrak musiman saat ini telah berakhir" in txt_lower:
                ctx.contract_ended = True

            # Salary amount override
            if any(k in txt_lower for k in ["salary", "gaji", "monthly pay", "base salary"]):
                amt_match = re.search(r"(?:is|be|to|menjadi|adalah)\s+(EUR|USD|IDR|INR|ZAR)\s*([\d,]+(?:\.\d+)?)", txt, re.IGNORECASE)
                if amt_match:
                    ctx.salary_amount = float(amt_match.group(2).replace(",", ""))

            # Pending holds / non-withdrawable credits
            if any(k in txt_lower for k in ["still pending", "masih menunggu", "not withdrawable", "belum disetujui", "has not reached your account"]):
                if m.related_event_id:
                    ctx.disregarded_event_ids.add(m.related_event_id)

        return ctx
