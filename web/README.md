# By Heart — Web Trainer

A FastAPI front-end that lets a real person memorize Robert Frost's *Stopping by Woods on
a Snowy Evening* while **watching the agents work**. It drives the **existing** By Heart
ADK 2.0 graphs and Prosody MCP unchanged — `app/` is imported by reference, never modified
— and streams each graph node transition to the browser, so the two graphs light up
node-by-node as you build the course and recall the poem.

This is an **additive** layer over the capstone MVP. The masking, semantic grading,
crutch-removal schedule, provenance allowlist, and minimal-PII guarantees all stay in
`app/`; this service only presents them.

## What you see

- **Build my course** drives **Graph A** live: `provenance_gate → prosody_analysis`
  (the Prosody **MCP** firing — watch the reasoning log) `→ curriculum_plan`, with the
  per-session **Deletion Rationale** rendered.
- **Recall** drives **Graph B** live: the masked stanza appears, the graph pauses at
  `present_masked_line` (the ADK `RequestInput` human-in-the-loop — "waiting for you"),
  you type the missing word, and `adjudicate → advance | scaffold → memory_update` lights
  up with your semantic grade and the **crutch-dependence tag**.
- **Re-plan from my pattern** rebuilds the course from *your* recorded recalls — and pulls
  a **different** crutch earlier when your pattern warrants it (the adaptive money shot).

## Run it locally

From the repo root (a [uv](https://docs.astral.sh/uv/) workspace):

```
uv sync                                   # installs the root package + this web member
cp .env.example .env                       # add a Gemini key: https://aistudio.google.com/apikey
uv run --package by-heart-web uvicorn by_heart_web.server:app --reload --app-dir web
```

Open <http://localhost:8000>. The provenance gate and the static graph topology work with
**no** key; building the course and grading recalls need a Gemini key (the same
`GOOGLE_API_KEY` / `GEMINI_API_KEY` the rest of By Heart uses).

Tests (key-free smoke):

```
uv run --package by-heart-web pytest web/tests -q
```

## Deploy to GCP (Cloud Run + Vertex AI)

The app is Vertex-ready with **no code change** — the switch is environment only:

```
docker build -f web/Dockerfile -t by-heart-web .          # build from the repo root
# push to Artifact Registry, then deploy:
gcloud run deploy by-heart-web --image <IMAGE> \
  --set-env-vars GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=<PROJECT>,GOOGLE_CLOUD_LOCATION=us-central1
```

Give the service account `roles/aiplatform.user`. No `.env` ships in the image; secrets
come from Cloud Run config / Secret Manager. Locally (no Vertex vars) it uses the Gemini
Developer API key instead. `google-cloud-aiplatform` is declared for future Vertex
features; the running app reaches Gemini through `google-genai` either way.

> Note: the in-memory ADK session store and the `var/` JSON learner store are
> process-local — perfect for the demo and a single instance. Horizontal scaling later
> would point `BY_HEART_STATE_DIR` at GCS/Firestore and use a persistent ADK session
> service (additive, no change to `app/`).
