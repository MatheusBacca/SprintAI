"""Jira e Bitbucket simulados com estado mutável, para testar o sync ciclo a ciclo."""

import json
import re
from dataclasses import dataclass, field
from typing import Any

import httpx
import respx

SITE = "https://weon.atlassian.net"
BB = "https://api.bitbucket.org/2.0"

FIELDS = [
    {
        "id": "customfield_10020",
        "name": "Sprint",
        "custom": True,
        "schema": {"type": "array", "custom": "com.pyxis.greenhopper.jira:gh-sprint"},
    },
    {
        "id": "customfield_10026",
        "name": "Story Points",
        "custom": True,
        "schema": {"type": "number"},
    },
]


def sprint(sid: int, name: str, state: str, end: str = "2026-09-11T21:00:00.000Z") -> dict:
    return {
        "id": sid,
        "name": name,
        "state": state,
        "originBoardId": 144,
        "startDate": "2026-09-01T11:00:00.000Z",
        "endDate": end,
        "completeDate": end if state == "closed" else None,
    }


@dataclass
class FakeIssue:
    key: str
    summary: str
    updated: str = "2026-09-10T10:00:00.000+0000"
    sprints: list[int] = field(default_factory=list)
    parent: str | None = None
    issue_type: str = "Tarefa"
    assignee: str | None = None
    comments: list[str] = field(default_factory=list)
    links: list[tuple[str, str]] = field(default_factory=list)  # (tipo, chave destino)
    # (id, campo, de, para, quando, accountId do autor)
    changelog: list[tuple[str, str, str, str, str, str]] = field(default_factory=list)


class FakeJira:
    def __init__(self) -> None:
        self.sprints = [
            sprint(3994, "Sprint 73 - Core", "active"),
            sprint(3995, "Sprint 73 - Growth", "active"),
            sprint(2404, "🛠️BUG-SUPORT", "future"),
            sprint(3961, "Sprint 72 - Growth", "closed", end="2026-09-05T21:00:00.000Z"),
            sprint(3954, "Sprint 69 - Growth", "closed", end="2026-08-10T21:00:00.000Z"),
        ]
        self.issues: dict[str, FakeIssue] = {}
        self.my_account = "acc-me"
        self.full_fetches: list[list[str]] = []
        self.listings: list[str] = []
        self.changelog_calls: list[str] = []

    def add(self, issue: FakeIssue) -> FakeIssue:
        self.issues[issue.key] = issue
        return issue

    def _sprint_payload(self, sid: int) -> dict:
        s = next((x for x in self.sprints if x["id"] == sid), None) or sprint(
            sid, f"Sprint {sid}", "closed"
        )
        return {"id": s["id"], "name": s["name"], "state": s["state"], "boardId": 144}

    def _full(self, issue: FakeIssue) -> dict:
        return {
            "id": str(abs(hash(issue.key)) % 10**8),
            "key": issue.key,
            "fields": {
                "summary": issue.summary,
                "status": {
                    "name": "Em Desenvolvimento",
                    "statusCategory": {"key": "indeterminate"},
                },
                "issuetype": {"name": issue.issue_type, "subtask": False},
                "assignee": {"accountId": issue.assignee, "displayName": "Dev"}
                if issue.assignee
                else None,
                "parent": {"key": issue.parent} if issue.parent else None,
                "created": "2026-09-01T10:00:00.000+0000",
                "updated": issue.updated,
                "labels": [],
                "components": [],
                "issuelinks": [
                    {
                        "id": f"{issue.key}-{i}",
                        "type": {"name": t, "inward": "is blocked by", "outward": "blocks"},
                        "outwardIssue": {
                            "key": target,
                            "fields": {
                                "summary": "x",
                                "issuetype": {
                                    "name": self.issues[target].issue_type
                                    if target in self.issues
                                    else "Tarefa"
                                },
                            },
                        },
                    }
                    for i, (t, target) in enumerate(issue.links)
                ],
                "comment": {
                    "total": len(issue.comments),
                    "comments": [
                        {
                            "id": f"{issue.key}-c{i}",
                            "author": {"displayName": "Dev"},
                            "body": {
                                "type": "doc",
                                "content": [
                                    {"type": "paragraph", "content": [{"type": "text", "text": c}]}
                                ],
                            },
                            "created": "2026-09-02T10:00:00.000+0000",
                        }
                        for i, c in enumerate(issue.comments)
                    ],
                },
                "customfield_10020": [self._sprint_payload(s) for s in issue.sprints] or None,
                "customfield_10026": 3,
            },
        }

    def _search(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        jql = body["jql"]
        if match := re.fullmatch(r"sprint = (\d+)( AND assignee = currentUser\(\))?", jql):
            self.listings.append(jql)
            sid = int(match.group(1))
            found = [i for i in self.issues.values() if sid in i.sprints]
            if match.group(2):
                found = [i for i in found if i.assignee == self.my_account]
            return httpx.Response(
                200,
                json={
                    "issues": [{"key": i.key, "fields": {"updated": i.updated}} for i in found],
                    "isLast": True,
                },
            )
        if jql.startswith("assignee = currentUser()"):
            self.listings.append("mine")
            found = [i for i in self.issues.values() if i.assignee == self.my_account]
            return httpx.Response(
                200,
                json={
                    "issues": [{"key": i.key, "fields": {"updated": i.updated}} for i in found],
                    "isLast": True,
                },
            )
        if match := re.fullmatch(r"key in \((.+)\)", jql):
            keys = match.group(1).split(",")
            self.full_fetches.append(keys)
            return httpx.Response(
                200,
                json={
                    "issues": [self._full(self.issues[k]) for k in keys if k in self.issues],
                    "isLast": True,
                },
            )
        return httpx.Response(400, json={"errorMessages": [f"JQL inesperada: {jql}"]})

    def mount(self, router: respx.MockRouter) -> None:
        router.get(f"{SITE}/rest/api/3/myself").mock(
            side_effect=lambda request: httpx.Response(200, json={"accountId": self.my_account})
        )
        router.get(f"{SITE}/rest/api/3/field").mock(return_value=httpx.Response(200, json=FIELDS))
        router.get(f"{SITE}/rest/agile/1.0/board/144").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 144,
                    "name": "Engenharia",
                    "type": "scrum",
                    "location": {"projectKey": "WAI", "projectName": "WeON"},
                },
            )
        )
        router.get(f"{SITE}/rest/agile/1.0/board/144/sprint").mock(
            side_effect=lambda request: httpx.Response(
                200, json={"isLast": True, "values": self.sprints}
            )
        )
        router.post(f"{SITE}/rest/api/3/search/jql").mock(side_effect=self._search)
        router.get(url__regex=rf"{SITE}/rest/api/3/issue/[^/]+/changelog").mock(
            side_effect=self._changelog
        )

    def _changelog(self, request: httpx.Request) -> httpx.Response:
        key = request.url.path.split("/")[-2]
        self.changelog_calls.append(key)
        issue = self.issues.get(key)
        values = [
            {
                "id": cid,
                "created": when,
                "author": {"accountId": author, "displayName": "Dev"},
                "items": [{"field": field_name, "fromString": before, "toString": after}],
            }
            for cid, field_name, before, after, when, author in (issue.changelog if issue else [])
        ]
        return httpx.Response(200, json={"values": values, "isLast": True})


class FakeBitbucket:
    def __init__(self) -> None:
        self.repos = {
            "monitoria": "2026-09-12T18:00:00+00:00",
            "organia-configs": "2026-09-12T18:00:00+00:00",
        }
        self.prs: dict[str, list[dict[str, Any]]] = {"monitoria": [], "organia-configs": []}
        self.branches: dict[str, list[dict[str, Any]]] = {"monitoria": [], "organia-configs": []}
        self.statuses: dict[tuple[str, int], list[str]] = {}
        self.comments: dict[tuple[str, int], list[dict[str, Any]]] = {}
        self.pr_queries: list[tuple[str, dict]] = []
        self.status_calls: list[tuple[str, int]] = []
        self.comment_calls: list[tuple[str, int]] = []
        self.branch_calls: list[str] = []
        self.rate_limit_repo: str | None = None
        self.me = "bb-me"

    def pr(
        self,
        repo: str,
        pid: int,
        branch: str,
        state: str = "OPEN",
        commit: str = "c1",
        updated: str = "2026-09-12T10:00:00+00:00",
        participants=None,
        author: str = "bb-outro",
        comment_count: int | None = None,
    ) -> dict:
        pr = {
            "id": pid,
            "title": f"PR {pid}",
            "state": state,
            "draft": False,
            "author": {"account_id": author, "display_name": author},
            "source": {"branch": {"name": branch}, "commit": {"hash": commit}},
            "destination": {"branch": {"name": "main"}},
            "participants": participants or [],
            "comment_count": comment_count,
            "updated_on": updated,
            "created_on": "2026-09-01T10:00:00+00:00",
            "links": {
                "html": {"href": f"https://bitbucket.org/weonrepo/{repo}/pull-requests/{pid}"}
            },
        }
        self.prs[repo] = [p for p in self.prs[repo] if p["id"] != pid] + [pr]
        return pr

    def comment(
        self,
        repo: str,
        pid: int,
        cid: int,
        body: str,
        *,
        author: str = "bb-outro",
        created: str = "2026-09-12T11:00:00+00:00",
        inline: dict[str, Any] | None = None,
        deleted: bool = False,
    ) -> dict:
        """Adiciona um comentário e já acerta o `comment_count` do PR (é ele que dispara a busca)."""
        comment = {
            "id": cid,
            "user": {"account_id": author, "display_name": author},
            "content": {"raw": body, "html": f"<p>{body}</p>"},
            "created_on": created,
            "updated_on": created,
            "deleted": deleted,
            **({"inline": inline} if inline else {}),
        }
        bucket = self.comments.setdefault((repo, pid), [])
        bucket[:] = [c for c in bucket if c["id"] != cid] + [comment]
        for pr in self.prs[repo]:
            if pr["id"] == pid:
                pr["comment_count"] = len([c for c in bucket if not c["deleted"]])
        return comment

    def _repos(self, request: httpx.Request) -> httpx.Response:
        q = request.url.params.get("q", "")
        slugs = re.findall(r'slug = "([^"]+)"', q)
        values = [
            {"slug": s, "name": s, "updated_on": u, "mainbranch": {"name": "main"}}
            for s, u in self.repos.items()
            if not slugs or s in slugs
        ]
        return httpx.Response(200, json={"values": values})

    def _prs(self, request: httpx.Request, repo: str) -> httpx.Response:
        if repo == self.rate_limit_repo:
            return httpx.Response(429)
        params = request.url.params
        self.pr_queries.append((repo, {"state": params.get_list("state"), "q": params.get("q")}))
        states = set(params.get_list("state"))
        since = None
        if q := params.get("q"):
            since = q.split("> ", 1)[1]
        values = [
            p
            for p in self.prs[repo]
            if p["state"] in states and (since is None or p["updated_on"] > since)
        ]
        return httpx.Response(200, json={"values": values})

    def mount(self, router: respx.MockRouter) -> None:
        router.get(f"{BB}/user").mock(
            side_effect=lambda request: httpx.Response(
                200, json={"account_id": self.me, "uuid": "{uuid-me}"}
            )
        )
        router.get(f"{BB}/repositories/weonrepo").mock(side_effect=self._repos)
        for repo in self.repos:
            router.get(f"{BB}/repositories/weonrepo/{repo}/pullrequests").mock(
                side_effect=lambda request, repo=repo: self._prs(request, repo)
            )
            router.get(f"{BB}/repositories/weonrepo/{repo}/refs/branches").mock(
                side_effect=lambda request, repo=repo: (
                    self.branch_calls.append(repo),
                    httpx.Response(200, json={"values": self.branches[repo]}),
                )[1]
            )
        router.get(url__regex=rf"{BB}/repositories/weonrepo/[^/]+/pullrequests/\d+/statuses").mock(
            side_effect=self._statuses
        )
        router.get(url__regex=rf"{BB}/repositories/weonrepo/[^/]+/pullrequests/\d+/comments").mock(
            side_effect=self._comments
        )

    def _comments(self, request: httpx.Request) -> httpx.Response:
        parts = request.url.path.split("/")
        repo, pid = parts[-4], int(parts[-2])
        self.comment_calls.append((repo, pid))
        return httpx.Response(200, json={"values": self.comments.get((repo, pid), [])})

    def _statuses(self, request: httpx.Request) -> httpx.Response:
        parts = request.url.path.split("/")
        repo, pid = parts[-4], int(parts[-2])
        self.status_calls.append((repo, pid))
        return httpx.Response(
            200, json={"values": [{"state": s} for s in self.statuses.get((repo, pid), [])]}
        )
