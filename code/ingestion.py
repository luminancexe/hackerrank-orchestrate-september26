import csv
import os
from typing import Dict, List, Optional, Tuple
from code.models import (
    Request, FinancialProfile, FinancialEvent,
    PaymentOption, ExchangeRate, Message, ImageMapping
)

class DatasetLoader:
    def __init__(self, data_dir: str = 'dataset'):
        self.data_dir = data_dir
        self.profiles: Dict[str, FinancialProfile] = {}
        self.events: List[FinancialEvent] = []
        self.events_by_id: Dict[str, FinancialEvent] = {}
        self.events_by_user: Dict[str, List[FinancialEvent]] = {}
        self.payment_options: Dict[str, List[PaymentOption]] = {}
        self.exchange_rates: Dict[Tuple[str, str, str], float] = {}
        self.messages: List[Message] = []
        self.messages_by_user: Dict[str, List[Message]] = {}
        self.messages_by_request: Dict[str, List[Message]] = {}
        self.image_mappings: List[ImageMapping] = []
        self.image_by_event: Dict[str, ImageMapping] = {}

    def load_profiles(self) -> Dict[str, FinancialProfile]:
        path = os.path.join(self.data_dir, 'financial_profiles.csv')
        with open(path, encoding='utf-8') as f:
            for r in csv.DictReader(f):
                user_id = r['user_id']
                priorities = [p.strip() for p in r['financial_priorities'].split('|') if p.strip()]
                protect = set(p.strip() for p in r['expense_categories_to_protect'].split('|') if p.strip())
                reduce_cats = set(p.strip() for p in r['expense_categories_user_is_willing_to_reduce'].split('|') if p.strip())
                stop_cats = set(p.strip() for p in r['expense_categories_user_is_willing_to_stop'].split('|') if p.strip())
                methods = set(p.strip() for p in r['payment_methods_user_will_consider'].split('|') if p.strip())
                max_inst = int(r['max_installment_months']) if r['max_installment_months'].strip() else None
                
                profile = FinancialProfile(
                    user_id=user_id,
                    home_currency=r['home_currency'].strip(),
                    current_available_balance=float(r['current_available_balance']),
                    minimum_balance_to_keep=float(r['minimum_balance_to_keep']),
                    financial_priorities=priorities,
                    expense_categories_to_protect=protect,
                    expense_categories_user_is_willing_to_reduce=reduce_cats,
                    expense_categories_user_is_willing_to_stop=stop_cats,
                    payment_methods_user_will_consider=methods,
                    max_installment_months=max_inst
                )
                self.profiles[user_id] = profile
        return self.profiles

    def load_events(self) -> List[FinancialEvent]:
        path = os.path.join(self.data_dir, 'financial_events.csv')
        with open(path, encoding='utf-8') as f:
            for r in csv.DictReader(f):
                amt_str = r['amount'].strip()
                amt = float(amt_str) if amt_str else None
                min_amt_str = r['minimum_allowed_amount'].strip()
                min_amt = float(min_amt_str) if min_amt_str else None
                
                ev = FinancialEvent(
                    event_id=r['event_id'].strip(),
                    user_id=r['user_id'].strip(),
                    event_type=r['event_type'].strip(),
                    description=r['description'].strip(),
                    category=r['category'].strip(),
                    direction=r['direction'].strip(),
                    amount=amt,
                    currency=r['currency'].strip(),
                    event_date=r['event_date'].strip(),
                    settlement_date=r['settlement_date'].strip(),
                    status=r['status'].strip(),
                    linked_event_id=r['linked_event_id'].strip() if r['linked_event_id'].strip() else None,
                    flexibility=r['flexibility'].strip(),
                    minimum_allowed_amount=min_amt
                )
                self.events.append(ev)
                self.events_by_id[ev.event_id] = ev
                self.events_by_user.setdefault(ev.user_id, []).append(ev)
        return self.events

    def load_payment_options(self) -> Dict[str, List[PaymentOption]]:
        path = os.path.join(self.data_dir, 'request_payment_options.csv')
        with open(path, encoding='utf-8') as f:
            for r in csv.DictReader(f):
                freq = int(r['payment_frequency_days']) if r['payment_frequency_days'].strip() else None
                opt = PaymentOption(
                    payment_option_id=r['payment_option_id'].strip(),
                    request_id=r['request_id'].strip(),
                    payment_method=r['payment_method'].strip(),
                    payment_amount=float(r['payment_amount']),
                    number_of_payments=int(r['number_of_payments']),
                    first_payment_date=r['first_payment_date'].strip(),
                    payment_frequency_days=freq,
                    financing_fee=float(r['financing_fee']),
                    total_payable_amount=float(r['total_payable_amount'])
                )
                self.payment_options.setdefault(opt.request_id, []).append(opt)
        return self.payment_options

    def load_exchange_rates(self) -> Dict[Tuple[str, str, str], float]:
        path = os.path.join(self.data_dir, 'exchange_rates.csv')
        with open(path, encoding='utf-8') as f:
            for r in csv.DictReader(f):
                key = (r['rate_date'].strip(), r['from_currency'].strip(), r['to_currency'].strip())
                self.exchange_rates[key] = float(r['rate'])
        return self.exchange_rates

    def load_messages(self) -> List[Message]:
        path = os.path.join(self.data_dir, 'messages.csv')
        with open(path, encoding='utf-8') as f:
            for r in csv.DictReader(f):
                msg = Message(
                    message_id=r['message_id'].strip(),
                    user_id=r['user_id'].strip(),
                    request_id=r['request_id'].strip() if r['request_id'].strip() else None,
                    related_event_id=r['related_event_id'].strip() if r['related_event_id'].strip() else None,
                    sent_at=r['sent_at'].strip(),
                    source_type=r['source_type'].strip(),
                    message_text=r['message_text'].strip()
                )
                self.messages.append(msg)
                self.messages_by_user.setdefault(msg.user_id, []).append(msg)
                if msg.request_id:
                    self.messages_by_request.setdefault(msg.request_id, []).append(msg)
        return self.messages

    def load_images(self) -> List[ImageMapping]:
        path = os.path.join(self.data_dir, 'images.csv')
        with open(path, encoding='utf-8') as f:
            for r in csv.DictReader(f):
                img = ImageMapping(
                    image_id=r['image_id'].strip(),
                    user_id=r['user_id'].strip(),
                    request_id=r['request_id'].strip(),
                    related_event_id=r['related_event_id'].strip()
                )
                self.image_mappings.append(img)
                self.image_by_event[img.related_event_id] = img
        return self.image_mappings

    def load_requests(self, filename: str = 'requests.csv') -> List[Request]:
        path = os.path.join(self.data_dir, filename)
        requests = []
        with open(path, encoding='utf-8') as f:
            for r in csv.DictReader(f):
                req = Request(
                    request_id=r['request_id'].strip(),
                    user_id=r['user_id'].strip(),
                    request_date=r['request_date'].strip(),
                    request_type=r['request_type'].strip(),
                    requested_amount=float(r['requested_amount']),
                    desired_completion_date=r['desired_completion_date'].strip(),
                    allows_partial_payment=r['allows_partial_payment'].strip().lower() == 'true',
                    request_text=r['request_text'].strip()
                )
                requests.append(req)
        return requests

    def get_exchange_rate(self, date_str: str, from_curr: str, to_curr: str) -> float:
        if from_curr == to_curr:
            return 1.0
        # Direct lookup
        key = (date_str, from_curr, to_curr)
        if key in self.exchange_rates:
            return self.exchange_rates[key]
        # Closest available rate date for pair
        candidates = [(d, r) for (d, fc, tc), r in self.exchange_rates.items() if fc == from_curr and tc == to_curr]
        if candidates:
            # Sort by absolute distance in days or lexicographical date
            candidates.sort(key=lambda x: abs((int(x[0].replace('-', '')) - int(date_str.replace('-', '')))))
            return candidates[0][1]
        raise ValueError(f'No exchange rate found for {from_curr} -> {to_curr} near {date_str}')

    def normalize_event_currencies(self):
        for ev in self.events:
            profile = self.profiles.get(ev.user_id)
            if not profile:
                continue
            if ev.amount is not None:
                rate = self.get_exchange_rate(ev.settlement_date, ev.currency, profile.home_currency)
                ev.normalized_amount = round(ev.amount * rate, 2)
            if ev.minimum_allowed_amount is not None:
                rate = self.get_exchange_rate(ev.settlement_date, ev.currency, profile.home_currency)
                ev.minimum_allowed_amount = round(ev.minimum_allowed_amount * rate, 2)

    def load_all(self):
        self.load_profiles()
        self.load_events()
        self.load_payment_options()
        self.load_exchange_rates()
        self.load_messages()
        self.load_images()
        self.normalize_event_currencies()
