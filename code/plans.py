from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from code.models import FinancialProfile, FinancialEvent, Request, PaymentOption

@dataclass
class CandidatePlan:
    method: str
    affordability_status: str
    payment_schedule: List[Tuple[str, float]]
    payment_plan_str: str
    earliest_date_for_full_payment: Optional[str]
    spending_changes: List[str]
    spending_changes_str: str
    total_payable_amount: float
    first_payment_date: str
    last_payment_date: str
    number_of_payments: int
    payment_option_id: str = ""

class PaymentPlanEngine:
    def evaluate_schedule_safety(
        self,
        daily_balances: List[Tuple[str, float]],
        minimum_balance: float,
        schedule: List[Tuple[str, float]]
    ) -> bool:
        bal_dict = dict(daily_balances)
        dates = [d for d, _ in daily_balances]
        
        cumulative_deductions = [0.0] * len(daily_balances)
        sched_sorted = sorted(schedule, key=lambda x: x[0])
        
        for p_date, p_amt in sched_sorted:
            matched = False
            for idx, d in enumerate(dates):
                if d >= p_date:
                    cumulative_deductions[idx] += p_amt
                    matched = True
            if not matched and dates:
                # Beyond 90 days? Must fall within horizon or safely verified
                pass

        for idx, (d, bal) in enumerate(daily_balances):
            if round(bal - cumulative_deductions[idx], 2) < minimum_balance:
                return False

        return True

    def build_installment_schedule(self, option: PaymentOption) -> List[Tuple[str, float]]:
        schedule = []
        first_dt = datetime.strptime(option.first_payment_date, "%Y-%m-%d").date()
        freq = option.payment_frequency_days or 30
        for i in range(option.number_of_payments):
            cur_dt = first_dt + timedelta(days=i * freq)
            schedule.append((cur_dt.strftime("%Y-%m-%d"), option.payment_amount))
        return schedule

    def format_payment_plan(self, schedule: List[Tuple[str, float]]) -> str:
        if not schedule:
            return "none"
        parts = []
        for d, a in schedule:
            if round(a, 2) == int(round(a, 2)):
                parts.append(f"{d}:{int(round(a, 2))}")
            else:
                parts.append(f"{d}:{a:.2f}")
        return "|".join(parts)
