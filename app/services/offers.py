from datetime import datetime
from typing import List, Optional, Tuple
from pydantic import BaseModel
from app.models.offer import DiscountType

class CartItemInput(BaseModel):
    menu_item_id: int
    unit_price: float
    quantity: int

class OfferCandidate(BaseModel):
    id: int
    name: str
    discount_type: DiscountType
    discount_value: float
    priority: int
    stackable: bool
    max_uses_per_user: int
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    is_active: bool = True

class OfferEvaluationResult(BaseModel):
    applied_offer: Optional[OfferCandidate] = None
    discount_amount: float = 0.0
    reason: str

def calculate_offer_discount(offer: OfferCandidate, subtotal: float) -> float:
    """Calculate the precise monetary discount given subtotal and offer configuration."""
    if offer.discount_type == DiscountType.PERCENTAGE:
        raw_discount = subtotal * (offer.discount_value / 100.0)
    else:  # FIXED
        raw_discount = offer.discount_value
    # Discount cannot exceed subtotal
    return round(min(subtotal, max(0.0, raw_discount)), 2)

def evaluate_offers(
    items: List[CartItemInput],
    active_offers: List[OfferCandidate],
    user_usage_counts: dict[int, int],  # offer_id -> count of times user used this offer
    evaluation_time: Optional[datetime] = None,
) -> OfferEvaluationResult:
    """
    Tier 1 Pure Offers Engine (Section 5 of Specification).
    
    Inputs: cart items, active offers, user's past usage history, and evaluation timestamp.
    Outputs: Winning offer, discount amount, and resolution rationale.
    
    Core Rules:
    1. Filter: is_active == True.
    2. Filter: evaluation_time must fall within [start_time, end_time] window (if configured).
    3. Filter: user_usage_counts[offer.id] < offer.max_uses_per_user.
    4. Deterministic Conflict Resolution (Architecture Lock):
       - Primary: Higher priority wins.
       - Secondary tie-break: Larger calculated discount value wins.
       - Final tie-break: Lower stable offer ID wins.
       
    Property: NEVER depends on input list ordering. Calling this with any permutation of
    the offer list produces the exact identical result.
    """
    if not items or not active_offers:
        return OfferEvaluationResult(applied_offer=None, discount_amount=0.0, reason="No items or offers available")

    now = evaluation_time or datetime.now()
    subtotal = sum(i.unit_price * i.quantity for i in items)
    if subtotal <= 0:
        return OfferEvaluationResult(applied_offer=None, discount_amount=0.0, reason="Subtotal is zero")

    eligible_candidates: List[Tuple[OfferCandidate, float]] = []

    for offer in active_offers:
        # Rule 1: Active check
        if not offer.is_active:
            continue

        # Rule 2: Showtime/Time window check
        if offer.start_time and now < offer.start_time:
            continue
        if offer.end_time and now > offer.end_time:
            continue

        # Rule 3: Per-user usage cap enforcement
        used_count = user_usage_counts.get(offer.id, 0)
        if used_count >= offer.max_uses_per_user:
            continue

        # Calculate discount for this offer
        discount = calculate_offer_discount(offer, subtotal)
        if discount > 0:
            eligible_candidates.append((offer, discount))

    if not eligible_candidates:
        return OfferEvaluationResult(applied_offer=None, discount_amount=0.0, reason="No eligible offers matched")

    # Deterministic Sort Key:
    # 1. -priority (highest priority first)
    # 2. -discount (larger discount first)
    # 3. +offer.id (lowest offer id first for stable tie-break)
    eligible_candidates.sort(key=lambda pair: (-pair[0].priority, -pair[1], pair[0].id))

    winning_offer, winning_discount = eligible_candidates[0]

    return OfferEvaluationResult(
        applied_offer=winning_offer,
        discount_amount=winning_discount,
        reason=f"Applied offer '{winning_offer.name}' with discount {winning_discount}",
    )
