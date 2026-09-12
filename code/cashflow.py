from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict, Counter
from code.models import FinancialProfile, FinancialEvent, Request
from code.resolver import UserMessageContext

RECURRING_CATEGORIES = {
    "rent", "housing", "utilities", "insurance", "healthcare",
    "debt_repayment", "education", "cloud_storage", "streaming",
    "music_subscription", "delivery_membership", "gym", "family_support"
}

@dataclass
class RecurringStream:
    category: str
    description: str
    day_of_month: int
    amount: float
    is_income: bool
    flexibility: str = "fixed"
    minimum_allowed_amount: Optional[float] = None
    event_id: Optional[str] = None

class CashFlowEngine:
    def __init__(self, horizon_days: int = 90):
        self.horizon_days = horizon_days

    def extract_recurring_streams(
        self,
        profile: FinancialProfile,
        events: List[FinancialEvent],
        msg_ctx: UserMessageContext,
        request_date_str: str
    ) -> Tuple[List[RecurringStream], float]:
        req_dt = datetime.strptime(request_date_str, "%Y-%m-%d").date()
        streams = []

        # 1. Salary stream
        salary_events = [
            e for e in events 
            if e.category == "salary" and e.direction == "credit" and e.status in ("settled", "scheduled")
        ]
        salary_events.sort(key=lambda x: x.settlement_date)

        is_gig = any(
            any(w in e.description.lower() for w in ["platform payout", "app earnings", "marketplace"])
            for e in salary_events
        )
        is_final = any("final" in e.description.lower() for e in salary_events)
        
        has_confirmed_salary = (
            bool(salary_events) 
            and not is_gig 
            and not is_final 
            and not msg_ctx.contract_ended
        )

        if has_confirmed_salary:
            salary_amt = msg_ctx.salary_amount
            salary_day = None
            if msg_ctx.salary_date:
                salary_day = int(msg_ctx.salary_date.split("-")[2])
            elif salary_events:
                sal_days = [int(e.settlement_date.split("-")[2]) for e in salary_events]
                salary_day = Counter(sal_days).most_common(1)[0][0]
            else:
                salary_day = 15

            if salary_amt is None and salary_events:
                last_sal = salary_events[-1]
                salary_amt = last_sal.normalized_amount or last_sal.amount

            if salary_amt and salary_amt > 0:
                streams.append(RecurringStream(
                    category="salary",
                    description="Confirmed Monthly Salary",
                    day_of_month=salary_day,
                    amount=salary_amt,
                    is_income=True
                ))

        # 2. Monthly recurring expenses
        grouped = defaultdict(list)
        for e in events:
            if e.direction == "debit" and e.status == "settled" and e.settlement_date < request_date_str:
                amt = e.normalized_amount or e.amount
                if amt is not None and (e.category in RECURRING_CATEGORIES or "subscription" in e.category or "membership" in e.category):
                    grouped[(e.category, e.description, e.settlement_date[-2:])].append(e)

        for (cat, desc, dom), ev_list in grouped.items():
            if len(ev_list) >= 2 or cat in ("rent", "housing", "utilities", "education", "debt_repayment", "insurance") or "subscription" in cat or "membership" in cat:
                day_num = int(dom)
                latest_ev = max(ev_list, key=lambda x: x.settlement_date)
                amt = latest_ev.normalized_amount or latest_ev.amount

                if cat == "rent" and msg_ctx.rent_increase_pct > 0:
                    amt = round(amt * (1.0 + msg_ctx.rent_increase_pct / 100.0), 2)

                streams.append(RecurringStream(
                    category=cat,
                    description=desc,
                    day_of_month=day_num,
                    amount=amt,
                    is_income=False,
                    flexibility=latest_ev.flexibility,
                    minimum_allowed_amount=latest_ev.minimum_allowed_amount,
                    event_id=latest_ev.event_id
                ))

        # 3. Variable essential spending daily run-rate (groceries, transport)
        var_events = [
            e for e in events 
            if e.direction == "debit" and e.status == "settled" 
            and e.category in ("groceries", "transport") 
            and e.settlement_date < request_date_str
        ]
        var_daily = 0.0
        if var_events:
            total_var = sum(e.normalized_amount or e.amount or 0.0 for e in var_events)
            earliest_dt = datetime.strptime(min(e.settlement_date for e in var_events), "%Y-%m-%d").date()
            latest_dt = datetime.strptime(max(e.settlement_date for e in var_events), "%Y-%m-%d").date()
            span_days = max(30, (latest_dt - earliest_dt).days)
            var_daily = total_var / float(span_days)

        return streams, var_daily

    def simulate_daily_balances(
        self,
        profile: FinancialProfile,
        request_date_str: str,
        recurring_streams: List[RecurringStream],
        var_daily_rate: float,
        future_events: List[FinancialEvent],
        active_spending_changes: Optional[List[str]] = None
    ) -> List[Tuple[str, float]]:
        active_changes = active_spending_changes or []
        stopped_events = set()
        reduced_events = {}
        for ch in active_changes:
            if ch.startswith("stop:"):
                stopped_events.add(ch.split(":")[1])
            elif ch.startswith("reduce_to:"):
                parts = ch.split(":")
                reduced_events[parts[1]] = float(parts[2])

        req_dt = datetime.strptime(request_date_str, "%Y-%m-%d").date()
        daily_balances = []
        current_bal = profile.current_available_balance

        future_by_date = {}
        for fe in future_events:
            if fe.status in ("cancelled", "unrealized", "failed"):
                continue
            if fe.direction == "credit" and fe.status != "settled":
                continue
            future_by_date.setdefault(fe.settlement_date, []).append(fe)

        for day_offset in range(self.horizon_days + 1):
            cur_date = req_dt + timedelta(days=day_offset)
            date_str = cur_date.strftime("%Y-%m-%d")
            day_num = cur_date.day

            if day_offset > 0:
                current_bal -= var_daily_rate

            for st in recurring_streams:
                if day_num == st.day_of_month:
                    if day_offset == 0:
                        already_settled = any(
                            fe.settlement_date == date_str and fe.category == st.category
                            for fe in future_events if fe.status == "settled"
                        )
                        if already_settled:
                            continue
                    if st.is_income:
                        if day_offset > 0:
                            current_bal += st.amount
                    else:
                        if st.event_id in stopped_events:
                            continue
                        elif st.event_id in reduced_events:
                            current_bal -= reduced_events[st.event_id]
                        else:
                            current_bal -= st.amount

            if date_str in future_by_date:
                for fe in future_by_date[date_str]:
                    amt = fe.normalized_amount or fe.amount
                    if amt is None:
                        continue
                    if fe.direction == "debit":
                        current_bal -= amt
                    elif fe.direction == "credit" and fe.status == "settled":
                        current_bal += amt

            daily_balances.append((date_str, round(current_bal, 2)))

        return daily_balances

    def calculate_amount_safe_to_pay(
        self,
        daily_balances: List[Tuple[str, float]],
        minimum_balance: float,
        requested_amount: float
    ) -> float:
        min_balance_in_horizon = min(b for d, b in daily_balances)
        buffer = min_balance_in_horizon - minimum_balance
        safe = max(0.0, buffer)
        return min(requested_amount, round(safe, 2))

    def find_earliest_date_for_full_payment(
        self,
        daily_balances: List[Tuple[str, float]],
        minimum_balance: float,
        requested_amount: float,
        request_date_str: str,
        salary_day: Optional[int] = None
    ) -> Optional[str]:
        # Check if safe on request_date first
        req_safe = True
        for _, bal in daily_balances:
            if bal - requested_amount < minimum_balance:
                req_safe = False
                break
        if req_safe:
            return request_date_str

        # Scan candidate future dates (paydays)
        for idx, (d_str, _) in enumerate(daily_balances):
            if idx == 0:
                continue
            cur_dt = datetime.strptime(d_str, "%Y-%m-%d").date()
            if salary_day and cur_dt.day != salary_day:
                continue
            safe = True
            for t_idx in range(idx, len(daily_balances)):
                if daily_balances[t_idx][1] - requested_amount < minimum_balance:
                    safe = False
                    break
            if safe:
                return d_str
        return None
