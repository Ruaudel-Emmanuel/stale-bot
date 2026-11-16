# stale-bot

Déploiement du bot officiel **[actions/stale](https://github.com/actions/stale)** sur tous les
dépôts actifs du compte. **Complémentaire de GitHub-Auditor** (qui ne fait que *rapporter*) :
ici le bot *agit* — label « stale » puis fermeture automatique.

## ⚙️ Comportement (template `stale.yml`)

- **Cron natif GitHub** : `30 3 * * *` → 1x/jour à 03:30 UTC, sur les runners GitHub
  (aucune ressource VPS, pas de systemd timer). Déclenchable à la main : `workflow_dispatch`.
- **Issues** : stale après **60 j** sans activité → fermeture auto **14 j** après (74 j au total).
- **PR** : stale après **90 j**, fermeture **30 j** après.
- **Exemptions** : labels `pinned`, `security`. Le bot ignore toute issue/PR avec activité récente.
- Permissions du workflow : `issues: write`, `pull-requests: write` (GITHUB_TOKEN).


- Push direct sur `main` quand c'est autorisé.
- Si `main` est protégé (ruleset « PR requise ») → branche `chore/add-stale-bot` + **PR ouverte** :
  à merger manuellement (liste dans le rapport Telegram).
- Rapport Telegram à chaque déploiement. PAT : `Contents: read+write`.

## 🧪 Test

Après déploiement sur un repo, déclencher un run manuel :
Actions → « Stale issues & PRs » → Run workflow (ou API `workflow_dispatch`).
Vérifier ensuite l'onglet Issues : les issues inactives > 60 j portent le label `stale`.

## 🔒 Sécurité

Aucun secret dans ce repo. Le PAT reste dans `/home/ubuntu/.env` sur le VPS.
