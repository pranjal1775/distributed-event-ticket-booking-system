import os
import random


def process_payment(amount: float) -> bool:
    """
    Simulates payment processing.
    PAYMENT_MODE=success  → always True   (use in tests)
    PAYMENT_MODE=failure  → always False  (use in tests)
    PAYMENT_MODE=random   → 95% True      (default for dev/demo)
    """
    mode = os.getenv("PAYMENT_MODE", "random").lower()
    if mode == "success":
        return True
    if mode == "failure":
        return False
    return random.random() < 0.95
