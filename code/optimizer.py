import itertools
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
from code.models import FinancialProfile, FinancialEvent, Request, PaymentOption
from code.resolver import UserMessageContext
from code.cashflow import CashFlowEngine, RecurringStream
from code.plans import CandidatePlan, PaymentPlanEngine

class DecisionOptimizer:
    def __init__(self, cashflow_engine: CashFlowEngine, plan_engine: PaymentPlanEngine):
        self.cf_engine = cashflow_engine
        self.plan_engine = plan_engine

    def find_spending_change_candidates(
        self,
        profile: FinancialProfile,
        recurring_streams: List[RecurringStream]
    ) -> List[str]:
        candidates = []
        for st in recurring_streams:
            if not st.event_id or st.is_income:
                continue
            cat = st.category
            if cat in profile.expense_categories_to_protect:
                continue

            # Stoppable
            if cat in profile.expense_categories_user_is_willing_to_stop:
                if st.flexibility in ('stoppable', 'reducible_or_stoppable'):
                    candidates.append(f'stop:{st.event_id}')

            # Reducible
            if cat in profile.expense_categories_user_is_willing_to_reduce:
                if st.flexibility in ('reducible', 'reducible_or_stoppable') and st.minimum_allowed_amount is not None:
                    min_amt = st.minimum_allowed_amount
                    if min_amt == int(min_amt):
                        candidates.append(f'reduce_to:{st.event_id}:{int(min_amt)}')
                    else:
                        candidates.append(f'reduce_to:{st.event_id}:{min_amt:.2f}')

        return candidates

    def evaluate_request(
        self,
        request: Request,
        profile: FinancialProfile,
        events: List[FinancialEvent],
        payment_options: List[PaymentOption],
        msg_ctx: UserMessageContext
    ) -> CandidatePlan:
        streams, var_rate = self.cf_engine.extract_recurring_streams(
            profile, events, msg_ctx, request.request_date
        )
        sal_stream = next((s for s in streams if s.is_income), None)
        sal_day = sal_stream.day_of_month if sal_stream else None
        future_events = [e for e in events if e.settlement_date >= request.request_date]
        
        # Calculate baseline capacity
        base_daily = self.cf_engine.simulate_daily_balances(
            profile, request.request_date, streams, var_rate, future_events
        )
        base_safe = self.cf_engine.calculate_amount_safe_to_pay(
            base_daily, profile.minimum_balance_to_keep, request.requested_amount
        )
        base_earliest = self.cf_engine.find_earliest_date_for_full_payment(
            base_daily, profile.minimum_balance_to_keep, request.requested_amount,
            request.request_date, sal_day
        )

        allowed_methods = profile.payment_methods_user_will_consider
        spending_candidates = self.find_spending_change_candidates(profile, streams)

        # Generate candidate spending change sets: depth 0 first
        spending_combos = [[]]
        for r in range(1, min(4, len(spending_candidates) + 1)):
            for combo in itertools.combinations(spending_candidates, r):
                target_events = [c.split(':')[1] for c in combo]
                if len(target_events) == len(set(target_events)):
                    spending_combos.append(list(combo))

        valid_plans: List[CandidatePlan] = []

        for changes in spending_combos:
            num_changes = len(changes)
            ch_str = '|'.join(changes) if changes else 'none'

            # Simulate daily balance with these spending changes
            if not changes:
                daily = base_daily
                earliest = base_earliest
            else:
                daily = self.cf_engine.simulate_daily_balances(
                    profile, request.request_date, streams, var_rate, future_events, changes
                )
                earliest = self.cf_engine.find_earliest_date_for_full_payment(
                    daily, profile.minimum_balance_to_keep, request.requested_amount,
                    request.request_date, sal_day
                )

            # 1. Full Payment candidate
            if 'full_payment' in allowed_methods:
                sched = [(request.request_date, request.requested_amount)]
                if self.plan_engine.evaluate_schedule_safety(daily, profile.minimum_balance_to_keep, sched):
                    if request.request_date <= request.desired_completion_date:
                        status = 'affordable_now' if num_changes == 0 else 'affordable_with_plan'
                        valid_plans.append(CandidatePlan(
                            method='full_payment',
                            affordability_status=status,
                            payment_schedule=sched,
                            payment_plan_str=self.plan_engine.format_payment_plan(sched),
                            earliest_date_for_full_payment=request.request_date if num_changes == 0 else base_earliest,
                            spending_changes=changes,
                            spending_changes_str=ch_str,
                            total_payable_amount=request.requested_amount,
                            first_payment_date=request.request_date,
                            last_payment_date=request.request_date,
                            number_of_payments=1
                        ))

            # 2. Wait (Full payment later) candidate
            if num_changes == 0 and 'full_payment' in allowed_methods and earliest and earliest > request.request_date:
                sched = [(earliest, request.requested_amount)]
                if self.plan_engine.evaluate_schedule_safety(daily, profile.minimum_balance_to_keep, sched):
                    if earliest <= request.desired_completion_date:
                        valid_plans.append(CandidatePlan(
                            method='wait',
                            affordability_status='affordable_later',
                            payment_schedule=sched,
                            payment_plan_str=self.plan_engine.format_payment_plan(sched),
                            earliest_date_for_full_payment=earliest,
                            spending_changes=[],
                            spending_changes_str='none',
                            total_payable_amount=request.requested_amount,
                            first_payment_date=earliest,
                            last_payment_date=earliest,
                            number_of_payments=1
                        ))

            # 3. Partial Payment candidate
            if request.allows_partial_payment and 'partial_payment' in allowed_methods:
                if 0 < base_safe < request.requested_amount and base_earliest and base_earliest <= request.desired_completion_date:
                    sched = [
                        (request.request_date, base_safe),
                        (base_earliest, round(request.requested_amount - base_safe, 2))
                    ]
                    if self.plan_engine.evaluate_schedule_safety(daily, profile.minimum_balance_to_keep, sched):
                        valid_plans.append(CandidatePlan(
                            method='partial_payment',
                            affordability_status='affordable_with_plan',
                            payment_schedule=sched,
                            payment_plan_str=self.plan_engine.format_payment_plan(sched),
                            earliest_date_for_full_payment=base_earliest,
                            spending_changes=changes,
                            spending_changes_str=ch_str,
                            total_payable_amount=request.requested_amount,
                            first_payment_date=request.request_date,
                            last_payment_date=base_earliest,
                            number_of_payments=2
                        ))

            # 4. Installment candidates
            if 'installments' in allowed_methods:
                for opt in payment_options:
                    if opt.payment_method != 'installments':
                        continue
                    if profile.max_installment_months and opt.number_of_payments > profile.max_installment_months:
                        continue
                    sched = self.plan_engine.build_installment_schedule(opt)
                    last_d = sched[-1][0]
                    if last_d <= request.desired_completion_date:
                        if self.plan_engine.evaluate_schedule_safety(daily, profile.minimum_balance_to_keep, sched):
                            valid_plans.append(CandidatePlan(
                                method='installments',
                                affordability_status='affordable_with_plan',
                                payment_schedule=sched,
                                payment_plan_str=self.plan_engine.format_payment_plan(sched),
                                earliest_date_for_full_payment=base_earliest,
                                spending_changes=changes,
                                spending_changes_str=ch_str,
                                total_payable_amount=opt.total_payable_amount,
                                first_payment_date=sched[0][0],
                                last_payment_date=last_d,
                                number_of_payments=opt.number_of_payments,
                                payment_option_id=opt.payment_option_id
                            ))

            if num_changes == 0 and any(p.last_payment_date <= request.desired_completion_date for p in valid_plans):
                break

        on_time_plans = [p for p in valid_plans if p.last_payment_date <= request.desired_completion_date]

        if on_time_plans:
            on_time_plans.sort(key=lambda p: (
                0 if p.last_payment_date <= request.desired_completion_date else 1,
                len(p.spending_changes),
                round(p.total_payable_amount, 2),
                p.first_payment_date,
                p.number_of_payments,
                p.payment_option_id if p.payment_option_id else 'zzzz'
            ))
            return on_time_plans[0]

        return CandidatePlan(
            method='not_recommended',
            affordability_status='not_affordable',
            payment_schedule=[],
            payment_plan_str='none',
            earliest_date_for_full_payment=base_earliest,
            spending_changes=[],
            spending_changes_str='none',
            total_payable_amount=0.0,
            first_payment_date='',
            last_payment_date='',
            number_of_payments=0
        )
