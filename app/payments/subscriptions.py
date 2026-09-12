"""
Subscription flow, hackathon-MVP version:

  1. Subscriber sends settings.subscription_price_usd of the configured
     stablecoin directly to settings.tempo_operator_address from their own
     wallet (a plain wallet-to-wallet TIP-20 transfer — no contract/checkout
     UI needed for a demo).
  2. Subscriber tells the API their wallet address + the resulting tx hash:
     POST /api/subscribe {"wallet_address": "...", "tx_hash": "..."}
  3. `activate_subscription()` verifies that tx on-chain (real amount, real
     recipient, not just trusting the claim) via
     tempo_adapter.verify_incoming_payment, then marks them active for
     settings.subscription_period_days.

This is intentionally the simplest thing that's still honest (on-chain
verified, not just recorded) rather than a full recurring-billing contract —
that's a real post-hackathon upgrade (Tempo Zones would live here: run this
same flow inside a Zone so the subscriber's payment amount/identity isn't
publicly visible, only to the operator + any auditor with a viewing key).
"""
from datetime import datetime, timedelta

from app.config import settings
from app.models import Subscriber, get_session, init_db
from app.payments import tempo_adapter


class SubscriptionError(Exception):
    pass


def activate_subscription(wallet_address: str, tx_hash: str) -> dict:
    init_db()
    if not settings.tempo_operator_address:
        raise SubscriptionError("TEMPO_OPERATOR_ADDRESS is not set — nowhere to verify payment against.")

    paid = tempo_adapter.verify_incoming_payment(
        tx_hash=tx_hash,
        expected_to=settings.tempo_operator_address,
        expected_min_amount_usd=settings.subscription_price_usd,
    )
    if not paid:
        raise SubscriptionError(
            f"Transaction {tx_hash} doesn't show a payment of at least "
            f"${settings.subscription_price_usd} to {settings.tempo_operator_address}."
        )

    session = get_session()
    try:
        sub = session.query(Subscriber).filter(Subscriber.wallet_address == wallet_address).first()
        now = datetime.utcnow()
        next_due = now + timedelta(days=settings.subscription_period_days)
        if sub is None:
            sub = Subscriber(
                wallet_address=wallet_address, status="active",
                last_payment_at=now, last_payment_tx_hash=tx_hash,
                next_payment_due=next_due, total_paid_usd=settings.subscription_price_usd,
            )
            session.add(sub)
        else:
            sub.status = "active"
            sub.last_payment_at = now
            sub.last_payment_tx_hash = tx_hash
            # Extend from whichever is later: today, or their current expiry
            # (so renewing early doesn't lose the remaining paid period).
            sub.next_payment_due = max(next_due, sub.next_payment_due or now)
            sub.total_paid_usd = (sub.total_paid_usd or 0) + settings.subscription_price_usd
        session.commit()
        session.refresh(sub)
        return _to_dict(sub)
    finally:
        session.close()


def is_active(wallet_address: str) -> bool:
    session = get_session()
    try:
        sub = session.query(Subscriber).filter(Subscriber.wallet_address == wallet_address).first()
        if sub is None or sub.status != "active":
            return False
        if sub.next_payment_due and sub.next_payment_due < datetime.utcnow():
            sub.status = "past_due"
            session.commit()
            return False
        return True
    finally:
        session.close()


def _to_dict(sub: Subscriber) -> dict:
    return {
        "wallet_address": sub.wallet_address,
        "status": sub.status,
        "last_payment_at": sub.last_payment_at.isoformat() if sub.last_payment_at else None,
        "next_payment_due": sub.next_payment_due.isoformat() if sub.next_payment_due else None,
        "total_paid_usd": sub.total_paid_usd,
    }
