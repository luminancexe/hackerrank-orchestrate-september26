from datetime import datetime
from typing import Dict, List, Optional
from code.models import FinancialProfile, FinancialEvent, Request
from code.plans import CandidatePlan

def format_currency_amount(amount: float, currency: str) -> str:
    if amount == int(amount):
        return f"{currency} {int(amount):,}"
    else:
        return f"{currency} {amount:,.2f}"

def format_date_natural(date_str: str) -> str:
    if not date_str:
        return ""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.strftime("%d %B %Y").lstrip("0")

class ExplanationGenerator:
    def generate_explanation(
        self,
        plan: CandidatePlan,
        request: Request,
        profile: FinancialProfile,
        events_by_id: Dict[str, FinancialEvent]
    ) -> str:
        curr = profile.home_currency
        min_bal_str = format_currency_amount(profile.minimum_balance_to_keep, curr)
        req_amt_str = format_currency_amount(request.requested_amount, curr)

        if plan.method == "full_payment" and plan.affordability_status == "affordable_now":
            return f"Pay {req_amt_str} today. This leaves at least {min_bal_str} available over the next 90 days."

        elif plan.method == "installments":
            first_d_str = format_date_natural(plan.first_payment_date)
            inst_amt = plan.payment_schedule[0][1] if plan.payment_schedule else 0.0
            inst_amt_str = format_currency_amount(inst_amt, curr)
            return f"Use {plan.number_of_payments} installments of {inst_amt_str}, starting {first_d_str}. This leaves at least {min_bal_str} available."

        elif plan.method == "wait":
            earliest_d_str = format_date_natural(plan.earliest_date_for_full_payment)
            return f"Pay {req_amt_str} in full on {earliest_d_str}. Paying earlier would take the balance below the {min_bal_str} minimum."

        elif plan.method == "partial_payment":
            first_amt = plan.payment_schedule[0][1]
            sec_amt = plan.payment_schedule[1][1]
            earliest_d_str = format_date_natural(plan.earliest_date_for_full_payment)
            return f"Pay {format_currency_amount(first_amt, curr)} today and the remaining {format_currency_amount(sec_amt, curr)} on {earliest_d_str}. This completes the full request and keeps the {min_bal_str} minimum protected."

        elif plan.method == "full_payment" and plan.spending_changes:
            # Describe spending changes
            action_phrases = []
            for ch in plan.spending_changes:
                if ch.startswith("stop:"):
                    ev_id = ch.split(":")[1]
                    ev = events_by_id.get(ev_id)
                    desc = ev.description.lower() if ev else "subscription"
                    action_phrases.append(f"stop the {desc}")
                elif ch.startswith("reduce_to:"):
                    parts = ch.split(":")
                    ev_id = parts[1]
                    new_amt = float(parts[2])
                    ev = events_by_id.get(ev_id)
                    desc = ev.description.lower() if ev else "expense"
                    action_phrases.append(f"reduce the {desc} to {format_currency_amount(new_amt, curr)}")

            changes_desc = " and ".join(action_phrases).capitalize()
            return f"{changes_desc}, then pay {req_amt_str} today. This leaves at least {min_bal_str} available."

        else: # not_recommended
            deadline_str = format_date_natural(request.desired_completion_date)
            return f"Do not make this payment by {deadline_str}. None of the available options keeps the {min_bal_str} minimum protected."
