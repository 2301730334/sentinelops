# Jenkins CI (Phase 2)

The CI server runs in Docker and is fully defined as code:

| File | Purpose |
|---|---|
| `../Jenkinsfile` | The pipeline: Checkout → Install → Test (JUnit + coverage) → Build image → Smoke test → Package → Push |
| `Dockerfile` | Jenkins LTS + Docker CLI + Python 3 + plugins |
| `plugins.txt` | Plugins installed at image build time |
| `casc.yaml` | Configuration-as-Code: admin user, Docker Hub credential, global env, and the `sentinelops` multibranch job |
| `docker-compose.yml` | Jenkins controller + Docker-in-Docker engine (the official Jenkins-in-Docker layout) |
| `.env.example` | Secrets template. Copy it to `.env`, which git ignores |

## Start Jenkins

Requirements: Docker Desktop running, with about 3 GB of RAM free.

```powershell
cd C:\Projects\sentinelops\jenkins
copy .env.example .env
notepad .env          # set JENKINS_ADMIN_PASSWORD (and Docker Hub values, optional)
docker compose up -d --build
docker compose logs -f jenkins     # wait for "Jenkins is fully up and running", then Ctrl+C
```

Open http://localhost:8080 and sign in with `JENKINS_ADMIN_ID` / `JENKINS_ADMIN_PASSWORD`.
There's no setup wizard: plugins, credentials and the job already exist.

## How "build on every push" works

`casc.yaml` creates a **multibranch pipeline** called `SentinelOps`. Every
branch that contains a `Jenkinsfile` gets its own job. Jenkins re-scans the
GitHub repository **every 2 minutes**, so each `git push` (to any branch) starts
a build automatically within about 2 minutes. Use **Scan Multibranch Pipeline Now**
for an immediate scan.

The pipeline:

| Stage | What it does | Branches |
|---|---|---|
| Checkout | Clones the commit and computes the short git SHA | all |
| Install | Creates a virtualenv and installs `requirements-dev.txt` | all |
| Test | Runs `pytest` and publishes JUnit results and a coverage report (fails under 85 %) | all |
| Build image | `docker build` tagged `<repo>:<git-sha>` | all |
| Smoke test | Runs the image and waits until `/readyz` returns 200 | all |
| Package | Archives a source tarball, the image tag, and test/coverage reports | all |
| Push image | Pushes `:<git-sha>` and `:latest` (main) or `:develop` (develop) to Docker Hub | main, develop |

### Optional: instant builds with a GitHub webhook

GitHub can't reach `localhost`, so a webhook needs a public tunnel:

1. Run `ngrok http 8080` and copy the `https://….ngrok-free.app` URL.
2. In Jenkins, go to *Manage Jenkins → Security → Git plugin notifyCommit access tokens* and add a token.
3. On GitHub, go to *repo → Settings → Webhooks → Add webhook* and use this Payload URL:
   `https://<ngrok-url>/git/notifyCommit?url=https://github.com/2301730334/sentinelops.git&token=<token>`
   with content type `application/json` and just the push event.

## Docker Hub push (optional)

1. https://hub.docker.com → *Account settings → Personal access tokens* → create a token with **Read & Write** access.
2. Put your username and the token in `jenkins/.env` (`DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`).
3. Run `docker compose up -d` to restart Jenkins with the new values.

The token is stored as the Jenkins credential `dockerhub` and is only exposed
to the push step through `withCredentials` (masked in logs). Without these
values, the push stage is skipped.

## Screenshots for the report

- The *SentinelOps* multibranch job showing the branches
- A green pipeline in *Stage View*
- The *Test Result* trend and the *Coverage* report
- Archived artifacts on a build page
- The image on Docker Hub

## Stop / reset

```powershell
docker compose stop          # stop, keep data
docker compose down          # remove containers, keep volumes (jobs, history)
docker compose down -v       # wipe everything (Jenkins home, Docker cache)
```
