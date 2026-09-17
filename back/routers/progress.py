from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends

from database.pool import get_pool
from repositories import progress_repo
from schemas.progress_schemas import ProgressStagesIn, ProgressStagesOut, StageOut, StatusStageOut
from services import progress
from services.progress.stages import ProgressStages, Stage

router = APIRouter(tags=["progress"])

Pool = Annotated[asyncpg.Pool, Depends(get_pool)]


async def _payload(pool: asyncpg.Pool, stages: ProgressStages) -> ProgressStagesOut:
    rows = await progress_repo.distinct_statuses(pool)
    return ProgressStagesOut(
        stages=[StageOut(**vars(s)) for s in stages.stages],
        statuses=[
            StatusStageOut(
                status=row["status"],
                status_category=row["status_category"],
                issue_count=row["issue_count"],
                stage_id=(stage.id if (stage := stages.stage_of(row["status"])) else None),
            )
            for row in rows
        ],
    )


@router.get("/progress/stages", response_model=ProgressStagesOut)
async def get_stages(pool: Pool):
    """Etapas do progresso e em qual delas cai cada status que existe no espelho."""
    return await _payload(pool, await progress.load_stages(pool))


@router.put("/progress/stages", response_model=ProgressStagesOut)
async def put_stages(pool: Pool, body: ProgressStagesIn):
    stages = ProgressStages(
        stages=tuple(sorted((Stage(**s.model_dump()) for s in body.stages), key=lambda s: s.order)),
        statuses=dict(body.statuses),
    )
    return await _payload(pool, await progress.save_stages(pool, stages))
