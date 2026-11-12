#!/usr/bin/env python3
"""
deploy_stale.py — Déploie le workflow actions/stale (stale.yml) dans tous les dépôts actifs.

Pour chaque dépôt non archivé visible par le PAT :
  - si .github/workflows/stale.yml existe déjà -> ignoré (sauf --force)
  - sinon PUT direct sur main
  - si main est protégé (ruleset : PR requise) -> branche chore/add-stale-bot + PR ouverte

Rapport : stdout + Telegram. Exit 0 même s'il reste des PR à merger (c'est volontaire).

Usage :
  python3 deploy_stale.py                 # tous les dépôts actifs
  python3 deploy_stale.py --repo NOM      # un seul (test)
  python3 deploy_stale.py --force         # réécrire même si déjà présent
"""
import base64
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

API = "https://api.github.com"
ENV_PAT = "/home/ubuntu/.env"
ENV_TG = "/etc/vps-watchdog-telegram.env"
HERE = os.path.dirname(os.path.abspath(__file__))
STALE_YML = os.path.join(HERE, "stale.yml")
WORKFLOW_PATH = ".github/workflows/stale.yml"
BRANCH = "chore/add-stale-bot"


def get_pat():
    with open(ENV_PAT) as f:
        for line in f:
            if line.startswith("GITHUB_PAT="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit(f"GITHUB_PAT introuvable dans {ENV_PAT}")


def api(method, url, pat, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
        headers={"Authorization": f"Bearer {pat}", "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json", "X-GitHub-Api-Version": "2022-11-28"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}


def deploy_to_repo(full, pat, content_b64, force):
    """Retourne un statut : 'deployed' | 'exists' | 'pr' | 'error'."""
    st, cur = api("GET", f"{API}/repos/{full}/contents/{WORKFLOW_PATH}", pat)
    if st == 200 and not force:
        return "exists", None
    sha = cur.get("sha") if st == 200 else None
    body = {"message": "chore: ajoute le bot stale (actions/stale@v11, 1x/jour) [skip ci]",
            "content": content_b64, "branch": "main"}
    if sha:
        body["sha"] = sha
    st, res = api("PUT", f"{API}/repos/{full}/contents/{WORKFLOW_PATH}", pat, body)
    if st in (200, 201):
        return "deployed", None
    # main protégé -> branche + PR
    st, ref = api("GET", f"{API}/repos/{full}/git/ref/heads/main", pat)
    if st != 200:
        return "error", f"GET main: HTTP {st}"
    base_sha = ref["object"]["sha"]
    st, _ = api("POST", f"{API}/repos/{full}/git/refs", pat,
                {"ref": f"refs/heads/{BRANCH}", "sha": base_sha})
    if st not in (201, 422):  # 422 = branche existe déjà
        return "error", f"create branch: HTTP {st}"
    st, _ = api("PUT", f"{API}/repos/{full}/contents/{WORKFLOW_PATH}", pat,
                {"message": "chore: ajoute le bot stale [skip ci]", "content": content_b64, "branch": BRANCH})
    if st not in (200, 201):
        return "error", f"PUT branche: HTTP {st}"
    st, pr = api("POST", f"{API}/repos/{full}/pulls", pat,
                 {"title": "chore: bot stale (actions/stale@v11, 1x/jour)",
                  "head": BRANCH, "base": "main",
                  "body": "Ajoute `.github/workflows/stale.yml` : issues/PR inactifs labelisés « stale » puis fermés automatiquement. Déclenchable aussi à la main (workflow_dispatch)."})
    if st in (201, 422):
        return "pr", pr.get("html_url")
    return "error", f"create PR: HTTP {st}"


def send_telegram(text):
    try:
        with open(ENV_TG) as f:
            env = dict(l.strip().split("=", 1) for l in f if "=" in l)
        token, chat = env["TG_BOT_TOKEN"].strip('"'), env["TG_CHAT_ID"].strip('"')
        body = json.dumps({"chat_id": chat, "text": text[:4000]}).encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                     data=body, method="POST", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status == 200
    except Exception as e:
        print(f"(telegram non envoyé: {e})", file=sys.stderr)
        return False


def main():
    pat = get_pat()
    force = "--force" in sys.argv
    only_repo = sys.argv[sys.argv.index("--repo") + 1] if "--repo" in sys.argv else None
    content_b64 = base64.b64encode(open(STALE_YML, "rb").read()).decode()

    st, repos = api("GET", f"{API}/user/repos?per_page=100&type=all", pat)
    repos = [r["full_name"] for r in repos if not r.get("archived")]
    if only_repo:
        repos = [r for r in repos if r.endswith("/" + only_repo)]

    results = {"deployed": [], "exists": [], "pr": [], "error": []}
    for full in repos:
        status, info = deploy_to_repo(full, pat, content_b64, force)
        results[status].append((full, info))
        print(f"  {status:9s} {full}" + (f"  ({info})" if info else ""), flush=True)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"🤖 Déploiement bot stale (actions/stale@v11, cron 1x/jour natif GitHub) — {now}",
             f"✅ déployés: {len(results['deployed'])} · déjà en place: {len(results['exists'])} · "
             f"PR ouvertes (main protégé): {len(results['pr'])} · erreurs: {len(results['error'])}"]
    for full, url in results["pr"]:
        lines.append(f"  🔀 PR à merger: {full} -> {url}")
    for full, err in results["error"]:
        lines.append(f"  ❌ {full}: {err}")
    report = "\n".join(lines)
    print(report)
    send_telegram(report)
    sys.exit(1 if results["error"] else 0)


if __name__ == "__main__":
    main()
