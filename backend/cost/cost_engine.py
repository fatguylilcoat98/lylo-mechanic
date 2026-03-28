"""
The Good Neighbor Guard — LYLO Mechanic
Christopher Hughes · Sacramento, CA
AI Collaborators: Claude · GPT · Gemini · Groq
Truth · Safety · We Got Your Back

Cost engine: builds RepairCostEstimate for each hypothesis.
Enforces data freshness. Never presents stale pricing as current.
"""

import json
import os
from datetime import date, datetime
from typing import Optional, List
from models.schemas import RepairCostEstimate, CostTier, PartItem, DiagnosisHypothesis, DataConfidence

_PRICING_PATH = os.path.join(os.path.dirname(__file__), "../data/pricing/repair_costs.json")
_PRICING: dict = {}

MAX_AGE_DAYS = 365
STALE_WARNING_DAYS = 270


def _load_pricing():
    global _PRICING
    if not _PRICING:
        with open(_PRICING_PATH) as f:
            _PRICING = json.load(f)


def build_cost_estimates(
    hypotheses: List[DiagnosisHypothesis],
    confidence: DataConfidence,
) -> List[RepairCostEstimate]:
    """Build cost estimates for all hypotheses. Skip unknowns gracefully."""
    _load_pricing()

    if "cost_estimate" in confidence.blocked_outputs:
        return []

    estimates = []
    meta = _PRICING.get("_meta", {})
    data_date_str = meta.get("data_date", "2025-01-01")

    try:
        data_date = datetime.strptime(data_date_str, "%Y-%m-%d").date()
    except ValueError:
        data_date = date(2025, 1, 1)

    age_days = (date.today() - data_date).days

    if age_days > MAX_AGE_DAYS:
        # Do not return any estimates — data is too stale
        return []

    stale_warning = age_days > STALE_WARNING_DAYS

    for hyp in hypotheses:
        est = _build_single_estimate(hyp.cause_id, data_date_str, age_days, stale_warning, confidence)
        if est:
            estimates.append(est)

    return estimates


def _build_single_estimate(
    cause_id: str,
    data_date_str: str,
    age_days: int,
    stale_warning: bool,
    confidence: DataConfidence,
) -> Optional[RepairCostEstimate]:
    data = _PRICING.get(cause_id)
    if not data:
        return None

    # Apply confidence-based volatility upgrade
    volatility = data.get("volatility", "MEDIUM")
    if confidence.overall < 0.55:
        # Low confidence diagnosis → bump volatility
        if volatility == "LOW":
            volatility = "MEDIUM"
        elif volatility == "MEDIUM":
            volatility = "HIGH"

    diy_parts_low = data["diy_parts_low"]
    diy_parts_high = data["diy_parts_high"]
    tool_cost = data.get("diy_tool_cost", 0)

    diy = CostTier(
        label="DIY",
        total_low=diy_parts_low + tool_cost,
        total_high=diy_parts_high + tool_cost,
        parts_low=diy_parts_low,
        parts_high=diy_parts_high,
    )

    shop = CostTier(
        label="Independent Shop",
        total_low=data["shop_parts_low"] + data["shop_labor_low"],
        total_high=data["shop_parts_high"] + data["shop_labor_high"],
        parts_low=data["shop_parts_low"],
        parts_high=data["shop_parts_high"],
        labor_low=data["shop_labor_low"],
        labor_high=data["shop_labor_high"],
    )

    dealer = CostTier(
        label="Dealership",
        total_low=data["dealer_total_low"],
        total_high=data["dealer_total_high"],
        note=data.get("dealer_note"),
    )

    parts_list = [
        PartItem(
            part_name=p["name"],
            oem_part_number=None,
            aftermarket_note=p.get("oem_note"),
            qty=p.get("qty", 1),
            cost_low=p["low"],
            cost_high=p["high"],
        )
        for p in data.get("parts", [])
    ]

    uncertainty = list(data.get("uncertainty", []))
    if stale_warning:
        uncertainty.append(f"⚠ Pricing data is {age_days} days old — verify current prices before purchasing parts")

    return RepairCostEstimate(
        cause_id=cause_id,
        volatility=volatility,
        pricing_data_date=data_date_str,
        stale_warning=stale_warning,
        diy=diy,
        shop=shop,
        dealership=dealer,
        parts_list=parts_list,
        labor_hours_low=data.get("labor_hours_low", 0.5),
        labor_hours_high=data.get("labor_hours_high", 2.0),
        time_to_complete_diy=data.get("diy_time", "Varies"),
        uncertainty_factors=uncertainty,
        what_could_make_estimate_wrong=data.get("estimate_wrong_if", []),
    )
