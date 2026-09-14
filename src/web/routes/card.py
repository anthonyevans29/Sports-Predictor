"""
Daily card page — the web view of the same structured card the CLI `card`
command produces. Both call src.walters.card.build_card(), so the UI and CLI
can never drift apart.

The card is a fact assembler with honest flags: market disagreement is shown
as caution, not edge, until CLV proves otherwise. This page does not give bet
advice — it surfaces the model's numbers and deterministic cautions for the
user to interpret.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.walters.card import build_card

router = APIRouter(prefix="/card")


@router.get("", response_class=HTMLResponse)
async def card_page(request: Request, date: str | None = None):
    from src.web.app import templates  # late import to avoid circulars
    target = datetime.fromisoformat(date).date() if date else None
    card = build_card(target_date=target)
    return templates.TemplateResponse(
        request,
        "card.html",
        {"card": card, "games": card["games"], "date": card["date"]},
    )
