"""테스트용 가짜 GitHub 클라이언트. PR 커밋의 파일 내용은 기본적으로 로컬 파일과 같다고 가정한다."""
import re
from pathlib import Path

from core import github, hashing


class FakeGh(github.GhClient):
    def __init__(self, root: Path, repo: str = "acme/app"):
        self.root = root
        self.repo = repo
        self.routes: dict = {}
        self.calls: list = []
        self.issues: dict[int, dict] = {}
        self.comments: dict[int, list] = {}
        self.content_override: dict[str, str | None] = {}

    def review(self, pr=7, rid=99, state="APPROVED", reviewer="qa-lead", author="dev", commit="c" * 40,
               perm="write"):
        b = f"repos/{self.repo}"
        self.routes[f"{b}/pulls/{pr}/reviews/{rid}"] = {"state": state, "user": {"login": reviewer},
                                                       "commit_id": commit, "submitted_at": "2026-10-26T00:00:00Z"}
        self.routes[f"{b}/pulls/{pr}"] = {"user": {"login": author}}
        self.routes[f"{b}/collaborators/{reviewer}/permission"] = {"permission": perm}
        return f"https://github.com/{self.repo}/pull/{pr}#pullrequestreview-{rid}"

    def open_pr(self, pr=7, author="vibelabs-web"):
        """PR head 는 호출 시점의 로컬 HEAD (push 되어 있다고 가정)."""
        import subprocess
        def pull():
            head = subprocess.run(["git", "-C", str(self.root), "rev-parse", "HEAD"],
                                  capture_output=True, text=True).stdout.strip()
            return {"state": "open", "user": {"login": author}, "head": {"sha": head}}
        self.routes[f"repos/{self.repo}/pulls/{pr}"] = pull

    def api(self, path, method="GET", body=None):
        self.calls.append((method, path, body))
        m = re.match(rf"repos/{re.escape(self.repo)}/pulls/(\d+)/reviews$", path)
        if m and method == "POST":
            pr = int(m.group(1))
            rid = 7000 + len([c for c in self.calls if c[0] == "POST" and c[1].endswith("/reviews")])
            login = getattr(self, "bot_login", "gk[bot]")
            self.routes[f"repos/{self.repo}/pulls/{pr}/reviews/{rid}"] = {
                "state": "APPROVED" if body["event"] == "APPROVE" else body["event"],
                "user": {"login": login, "type": "Bot"}, "commit_id": body["commit_id"],
                "submitted_at": "2026-10-26T02:00:00Z", "body": body.get("body")}
            return {"id": rid, "html_url": f"https://github.com/{self.repo}/pull/{pr}#pullrequestreview-{rid}"}
        if callable(self.routes.get(path)):
            return self.routes[path]()
        if path in self.routes:
            r = self.routes[path]
            if isinstance(r, Exception):
                raise r
            return r
        b = f"repos/{self.repo}"
        m = re.match(rf"{re.escape(b)}/contents/(.+)\?ref=(\w+)$", path)
        if m:
            p = m.group(1)
            if p in self.content_override:
                return {"sha": self.content_override[p]}
            sha = hashing.git_blob_sha(self.root / p)
            if sha is None:
                raise github.GhError("GitHub 404", 404)
            return {"sha": sha}
        if re.match(rf"{re.escape(b)}/git/trees/\w+\?recursive=1$", path):
            tree = [{"path": f.relative_to(self.root).as_posix(), "type": "blob", "sha": hashing.git_blob_sha(f)}
                    for f in sorted((self.root / ".sdlc").rglob("*")) if f.is_file()]
            return {"tree": tree}
        return self._issues_api(b, path, method, body)

    def _issues_api(self, b, path, method, body):
        if path.startswith(f"{b}/labels"):
            return {}
        if path == f"{b}/issues" and method == "POST":
            n = len(self.issues) + 1
            self.issues[n] = {"number": n, "html_url": f"https://github.com/{self.repo}/issues/{n}",
                              "state": "open", **body}
            return self.issues[n]
        m = re.match(rf"{re.escape(b)}/issues/(\d+)(/comments)?(\?.*)?$", path)
        if m:
            n = int(m.group(1))
            if m.group(2):
                if method == "POST":
                    c = {"id": 1000 + sum(len(v) for v in self.comments.values()), "body": body["body"],
                         "user": {"login": "vibelabs-web"}, "created_at": "2026-10-26T01:00:00Z"}
                    self.comments.setdefault(n, []).append(c)
                    return c
                return list(self.comments.get(n, []))
            if method == "PATCH":
                self.issues[n].update(body)
                return self.issues[n]
            return self.issues[n]
        raise github.GhError(f"GitHub 404 {path}", 404)
