from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends

from database.pool import get_pool
from repositories import settings_repo
from schemas.preference_schemas import ShortcutsOut, ShortcutsPreferences
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
