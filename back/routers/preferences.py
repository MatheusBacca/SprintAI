from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends

from database.pool import get_pool
from repositories import settings_repo
from schemas.pr_status_schemas import ApprovalRuleSettings
from schemas.preference_schemas import (
    CardColorsIn,
    CardColorsOut,
    CardTypeColorOut,
    RepoColorOut,
    ShortcutsOut,
    ShortcutsPreferences,
)
from services import card_colors, pr_status_service
from services.card_colors import CARD_TYPES, SUGGESTED_COLORS, CardColors
from services.pr_status import ApprovalRule
from services.shortcuts import merge_with_defaults

router = APIRouter(prefix="/preferences", tags=["preferences"])

Pool = Annotated[asyncpg.Pool, Depends(get_pool)]

SHORTCUTS_KEY = "shortcuts"


@router.get("/shortcuts", response_model=ShortcutsOut)
async def get_shortcuts(pool: Pool):
    stored = await settings_repo.get_setting(pool, SHORTCUTS_KEY)
    return ShortcutsOut(bindings=merge_with_defaults(stored))


@router.put("/shortcuts", response_model=ShortcutsOut)
async def put_shortcuts(pool: Pool, payload: ShortcutsPreferences):
    await settings_repo.set_setting(pool, SHORTCUTS_KEY, payload.bindings)
    return ShortcutsOut(bindings=payload.bindings)


@router.get("/pr-approval", response_model=ApprovalRuleSettings)
async def get_pr_approval(pool: Pool):
    rule = await pr_status_service.load_rule(pool)
    return ApprovalRuleSettings(min_percent=rule.min_percent)


@router.put("/pr-approval", response_model=ApprovalRuleSettings)
async def put_pr_approval(pool: Pool, payload: ApprovalRuleSettings):
    """Quanto dos revisores precisa aprovar para o PR contar como "Aprovada"."""
    rule = await pr_status_service.save_rule(pool, ApprovalRule(min_percent=payload.min_percent))
    return ApprovalRuleSettings(min_percent=rule.min_percent)


def _card_colors_out(colors: CardColors) -> CardColorsOut:
    """Os repositórios são os escolhidos em Sincronização, mais os que saíram de lá com cor
    ou apelido — sem eles na lista, o que foi gravado ficaria sem ter por onde tirar."""
    synced = set(colors.known)
    return CardColorsOut(
        types=[
            CardTypeColorOut(
                id=t.id, label=t.label, color=colors.types.get(t.id), default_color=t.default_color
            )
            for t in CARD_TYPES
        ],
        repos=[
            RepoColorOut(
                slug=slug,
                color=colors.repos.get(slug),
                synced=slug in synced,
                aliases=list(colors.aliases.get(slug, ())),
                automatic_aliases=colors.automatic_aliases(slug),
            )
            for slug in sorted(synced | set(colors.repos) | set(colors.aliases))
        ],
        suggestions=list(SUGGESTED_COLORS),
    )


@router.get("/card-colors", response_model=CardColorsOut)
async def get_card_colors(pool: Pool):
    return _card_colors_out(await card_colors.load_colors(pool))


@router.put("/card-colors", response_model=CardColorsOut)
async def put_card_colors(pool: Pool, payload: CardColorsIn):
    """Cor do fundo dos cards do canvas: pelo tipo (pais) e pelo `[repo]` do título."""
    known = (await card_colors.load_colors(pool)).known
    colors = CardColors.from_setting(payload.model_dump(), known)
    return _card_colors_out(await card_colors.save_colors(pool, colors))
