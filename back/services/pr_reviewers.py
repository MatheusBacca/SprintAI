"""Reviewers dos PRs pelo SprintAI: escolher quem entra e tirar quem sai.

A lista de quem pode entrar são os membros do workspace do Bitbucket — buscada lá e guardada
em memória por meia hora: muda pouco, e cada abertura do seletor não pode virar uma rodada de
páginas na API. Nada disso vai para o banco.

A troca só vale para PR que o espelho conhece (um PR qualquer do workspace não é assunto do
SprintAI) e aberto. O Bitbucket troca a lista inteira de uma vez: a atual é lida na hora, o
pedido tira e põe, e o resto fica como estava — inclusive a aprovação de quem ficou. Tirar
quem já aprovou leva a aprovação junto; a tela avisa antes.

Depois da troca o sync roda, como no merge: a lista nova chega ao espelho pelo caminho de
sempre, com o evento.
"""

import time
from typing import Any

import asyncpg

from integrations import factory
from integrations.errors import BadRequest, PermissionDenied
from repositories import bitbucket_repo
from schemas.conclude_schemas import (
    BitbucketMemberOut,
    PrReviewerOut,
    PrReviewersOut,
    ReviewersIn,
)
from security.credential_store import CredentialStore
from services.issue_actions import IssueActionConflict
from services.progress.stages import normalize
from services.sync.engine import SyncEngine, sync_after_write
from services.sync.mappers import bitbucket_avatar

MEMBERS_TTL_SECONDS = 30 * 60

_members: dict[str, Any] = {"at": 0.0, "workspace": None, "list": []}


class PullRequestNotInMirror(Exception):
    pass


def _ids(user: dict[str, Any]) -> set[str]:
    return {i for i in (user.get("account_id"), user.get("uuid")) if i}


def _member(user: dict[str, Any], me: set[str]) -> BitbucketMemberOut:
    return BitbucketMemberOut(
        account_id=user.get("account_id"),
        uuid=user.get("uuid"),
        name=user.get("display_name") or user.get("nickname") or "?",
        nickname=user.get("nickname"),
        is_me=bool(_ids(user) & me),
    )


def _my_ids(store: CredentialStore) -> set[str]:
    data = store.get("bitbucket") or {}
    return {i for i in (data.get("account_id"),) if i}


async def members(store: CredentialStore, *, refresh: bool = False) -> list[BitbucketMemberOut]:
    data = store.get("bitbucket") or {}
    workspace = data.get("workspace")
    fresh = time.monotonic() - _members["at"] < MEMBERS_TTL_SECONDS
    if not refresh and fresh and _members["workspace"] == workspace and _members["list"]:
        return _members["list"]
    me = _my_ids(store)
    try:
        async with factory.bitbucket_client(store) as bb:
            found = [
                _member(user, me)
                async for user in bb.iter_workspace_members()
                if user.get("type", "user") == "user"
            ]
    except PermissionDenied as exc:
        raise PermissionDenied(
            "Bitbucket",
            "Bitbucket: o token não lê os membros do workspace — gere um com o escopo "
            "read:workspace:bitbucket (Configurações › Conexões).",
            403,
        ) from exc
    found.sort(key=lambda m: normalize(m.name))
    _members.update({"at": time.monotonic(), "workspace": workspace, "list": found})
    return found


def clear_members_cache() -> None:
    _members.update({"at": 0.0, "workspace": None, "list": []})


def reviewers_of(pr: dict[str, Any]) -> list[PrReviewerOut]:
    """Os reviewers do PR como o Bitbucket devolve, com a aprovação de cada um (que mora nos
    participantes)."""
    by_id: dict[str, dict[str, Any]] = {}
    for participant in pr.get("participants") or []:
        for ident in _ids(participant.get("user") or {}):
            by_id[ident] = participant
    out = []
    for user in pr.get("reviewers") or []:
        participant = next((by_id[i] for i in _ids(user) if i in by_id), {})
        out.append(
            PrReviewerOut(
                account_id=user.get("account_id"),
                uuid=user.get("uuid"),
                name=user.get("display_name") or user.get("nickname"),
                approved=bool(participant.get("approved")),
                state=participant.get("state"),
                avatar_url=bitbucket_avatar(user),
            )
        )
    return out


def _reference(user: dict[str, Any]) -> dict[str, str]:
    return {"uuid": user["uuid"]} if user.get("uuid") else {"account_id": user["account_id"]}


async def update(
    pool: asyncpg.Pool,
    store: CredentialStore,
    engine: SyncEngine | None,
    repo_slug: str,
    pr_id: int,
    payload: ReviewersIn,
) -> PrReviewersOut:
    if await bitbucket_repo.pull_request(pool, repo_slug, pr_id) is None:
        raise PullRequestNotInMirror(f"O PR #{pr_id} de {repo_slug} não está no espelho local.")
    remove = set(payload.remove)
    known = {i: m for m in await _members_or_empty(store) for i in _ids(m.model_dump())}

    async with factory.bitbucket_client(store) as bb:
        pr = await bb.get_pull_request(repo_slug, pr_id)
        if pr.get("state") != "OPEN":
            raise IssueActionConflict("Só PR aberto troca de reviewers.")
        keep = [u for u in pr.get("reviewers") or [] if not (_ids(u) & remove)]
        present = set().union(*(_ids(u) for u in keep)) if keep else set()
        wanted = [_reference(u) for u in keep]
        for ident in payload.add:
            if ident in present or ident in remove:
                continue
            member = known.get(ident)
            user = member.model_dump() if member else {"account_id": ident}
            if not (user.get("uuid") or user.get("account_id")):
                continue
            wanted.append(_reference(user))
            present |= _ids(user)
        try:
            updated = await bb.set_reviewers(repo_slug, pr_id, wanted, title=pr.get("title"))
        except PermissionDenied as exc:
            raise PermissionDenied(
                "Bitbucket",
                "Bitbucket: sem permissão para mudar os reviewers — o token precisa do escopo "
                "write:pullrequest:bitbucket, ou o seu usuário não pode editar este PR.",
                403,
            ) from exc
        except BadRequest as exc:
            raise BadRequest(
                "Bitbucket",
                "Bitbucket: a lista foi recusada (HTTP 400) — o autor do PR não pode ser "
                "reviewer dele.",
                400,
            ) from exc

    await sync_after_write(engine, "reviewers")
    return PrReviewersOut(repo_slug=repo_slug, pr_id=pr_id, reviewers=reviewers_of(updated))


async def _members_or_empty(store: CredentialStore) -> list[BitbucketMemberOut]:
    """Para achar o `uuid` de quem entra. Sem a lista (token sem o escopo), vai pelo id."""
    try:
        return await members(store)
    except Exception:  # noqa: BLE001 — a troca segue pelo account_id
        return []
