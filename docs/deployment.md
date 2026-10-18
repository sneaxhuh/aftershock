# Judging setup and hosting

The submission provides a reproducible local deployment. No hosted live deployment is currently claimed. Judges can run it on their own machine; the participant's laptop does not need to remain online.

[Hackathon rule 10](https://www.wemakedevs.org/hackathons/falkordb/rules) accepts a live deployment **or complete local setup instructions if the project cannot be deployed**. A working demo video is separately required.

## Reproduce the working application

Install Docker with Compose v2. Clone this repository, copy `.env.example` to `.env`, and privately set `GEMINI_API_KEY`. Start the complete stack:

```sh
docker compose up --build -d --wait
```

Open http://localhost:8000. Follow **Try the complete story** in the README. Live mode pauses explicitly if no model key or quota is available. For a model-free run of the same real graph, services, actions, and verifier:

```sh
AGENT_MODE=rehearsal docker compose up --build -d --wait
```

The console labels rehearsal mode. It is not presented as live model output.

```sh
docker compose exec -T api python -m aftershock.check_coordination
docker compose restart api
```

The first command verifies tenant isolation and handoffs using disposable graphs. The second restarts the controller while retaining graph memory and service state. Normal `docker compose down` preserves volumes. Do not use `down -v` unless deleting the demonstration's data is intended.

## Why a static host is insufficient

AFTERSHOCK runs FalkorDB, the controller/UI, and four separate sandbox containers. Every sandbox executes five HTTP services with independent files, process state, and SQLite data. A static frontend deployment cannot run this experiment pipeline.

The existing Compose stack can also run on a Docker-capable cloud VM with persistent storage. Free-tier capacity, account eligibility, and availability must be checked with the provider. This project does not substitute shared process directories for the documented sandbox container boundaries to fit a free web-service plan.

## Optional operator login for public demonstrations

Before exposing this operator console through an HTTPS reverse proxy, set these values privately in `.env`:

```dotenv
AFTERSHOCK_REQUIRE_AUTH=true
AFTERSHOCK_OPERATOR_USER=operator
AFTERSHOCK_OPERATOR_PASSWORD=replace-with-a-private-random-password-of-at-least-16-characters
AFTERSHOCK_SECURE_COOKIE=true
```

Recreate the API container after changing settings. The browser prompts for the operator credentials. All console assets, documentation, and API operations require the login; `/api/health` remains available to health probes. Required authentication fails closed at startup if a password is absent. Keep the example replacement value out of actual deployments and never publish real credentials.

This is one shared demonstration operator with access to both synthetic workspaces. It does not implement a production user directory or per-user workspace permissions. Keep FalkorDB and sandbox supervisor ports internal. The app has no Docker socket. The local default remains unauthenticated on loopback for convenient reproduction.
