# shots

Generic, open-source friendly tooling to capture high-res marketing screenshots of a SaaS app.

**Key idea**: you log in once manually; `shots` saves a Playwright `storage_state.json`. After that, it can run repeatedly headless, optionally guided by an LLM (vision) to navigate and/or crop.

## Install

```bash
python -m venv .venv
source .venv/bin/activate

pip install -e ".[llm,yaml]"
playwright install chromium
```

## Setup

```bash
cp shots.yaml.example shots.yaml   # edit with your app's URL and shots
cp .env.example .env                # add your OPENAI_API_KEY
```

Both `shots.yaml` and `.env` are gitignored.

## 1) One-time manual login

```bash
shots login --base-url https://your-app.example.com --out-dir shots_out
```

This writes `shots_out/storage_state.json`.

## 2) Run required screenshots from a config

```bash
export OPENAI_API_KEY=...
shots run-config --config shots.yaml --out-dir shots_out --use-llm --use-llm-crop --save-source
```

## Config format (YAML)

```yaml
base_url: https://your-app.example.com
start: /app

defaults:
  viewport_preset: desktop
  full_page: true
  max_nav_steps: 12

shots:
  - id: dashboard-hero
    description: >
      Capture the main dashboard with KPI cards and a chart visible.
      Navigate via the left nav if needed. Close any modal/tour/cookie overlay.
    url: /app/dashboard

  - id: integrations
    description: >
      Show Settings -> Integrations page listing available integrations.
    viewport_preset: laptop
```

## Notes

* `--use-llm` enables multi-step "acquire the shot" behavior: the model returns one action at a time until it says `done`.
* `--use-llm-crop` asks the model to choose a crop rectangle for a marketing-friendly framing.
* All navigation is kept **same-origin** as `base_url`.
