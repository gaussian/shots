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

## 2) Run screenshots from a config

```bash
export OPENAI_API_KEY=...
shots run-config --config shots.yaml --use-llm --use-llm-crop --save-source
```

### CLI flags

| Flag | Default | Description |
|------|---------|-------------|
| `--config` | (required) | Path to YAML/JSON config file |
| `--out-dir` | from config, or `shots_out` | Output directory (overrides config `out_dir`) |
| `--use-llm` | off | LLM-driven multi-step navigation |
| `--model` | `gpt-5.2` | OpenAI model for navigation/crop |
| `--use-llm-crop` | off | LLM picks a marketing-friendly crop rectangle |
| `--max-crop-retries` | `2` | Crop validation retry attempts |
| `--save-source` | off | Save uncropped source images alongside output |
| `--timeout-ms` | `10000` | Page-load / navigation timeout |
| `--action-timeout-ms` | `5000` | Timeout for clicks/typing (fail fast) |
| `--headed` | off | Show the browser window (debug) |
| `--viewport` | `desktop` | Fallback viewport preset (`desktop`, `laptop`, `tablet`, `mobile`) |
| `--viewport-w`, `--viewport-h`, `--scale` | from preset | Override viewport dimensions |
| `--full-page` | from config/preset | Capture full scrollable page |

## Config format (YAML)

### Simple (flat `shots` list)

Each shot is auto-wrapped into its own group with `output: png`.

```yaml
base_url: https://your-app.example.com
start: /app
out_dir: shots_out

defaults:
  viewport_preset: desktop
  full_page: true
  max_nav_steps: 12

shots:
  - id: dashboard-hero
    description: >
      Capture the main dashboard with KPI cards and a chart visible.
      Close any modal, cookie banner, or tour overlay.
    url: /app/dashboard

  - id: integrations
    description: >
      Show Settings -> Integrations page listing available integrations.
    viewport_preset: laptop
```

### Groups (multi-shot PDFs, labels, folders)

Use `groups` instead of `shots` for more control. Each group produces either a single PNG or a multi-page PDF.

```yaml
base_url: https://your-app.example.com
start: /app
out_dir: shots_out

defaults:
  viewport_preset: desktop
  full_page: true
  max_nav_steps: 12

groups:
  - id: hero-shots
    output: png
    shots:
      - id: dashboard-hero
        description: >
          Capture the main dashboard.
        url: /app/dashboard

  - id: onboarding-deck
    output: pdf
    folder: onboarding
    label: "{id} — {url}"
    label_date: true
    shots:
      - id: step-1-welcome
        description: Show the welcome screen.
        url: /app/onboarding
      - id: step-2-profile
        description: Show the profile setup page.
        url: /app/onboarding/profile
```

### Config reference

| Field | Level | Description |
|-------|-------|-------------|
| `base_url` | top | (required) App base URL |
| `start` | top | Default start path (default: `/`) |
| `out_dir` | top | Output directory (default: `shots_out`, overridden by `--out-dir`) |
| `defaults.viewport_preset` | top | `desktop` \| `laptop` \| `tablet` \| `mobile` |
| `defaults.full_page` | top | Capture full scrollable page |
| `defaults.max_nav_steps` | top | Max LLM navigation steps per shot (default: `12`) |
| `shots` | top | Flat list of shots (cannot coexist with `groups`) |
| `groups` | top | List of shot groups (cannot coexist with `shots`) |
| `groups[].id` | group | (required) Group identifier |
| `groups[].output` | group | `png` (1 shot max) or `pdf` (multi-shot) |
| `groups[].folder` | group | Override output subfolder name (defaults to group id) |
| `groups[].label` | group | Label template applied to all shots (`{id}`, `{url}`, `{title}`) |
| `groups[].label_date` | group | Append UTC timestamp below label |
| `id` | shot | (required) Shot identifier |
| `description` | shot | (required) What to capture (used as LLM goal) |
| `url` | shot | Start URL for this shot (absolute or relative to `base_url`) |
| `viewport_preset` | shot | Override viewport for this shot |
| `viewport` | shot | Custom `{width, height, scale}` |
| `full_page` | shot | Override full-page capture for this shot |
| `label` | shot | Per-shot label override |

## Notes

* `--use-llm` enables multi-step navigation: the model sees a screenshot + accessibility tree each step and returns one action at a time until it says `done`.
* `--use-llm-crop` asks the model to choose a crop rectangle for marketing-friendly framing, with automatic validation and retry.
* All navigation is kept **same-origin** as `base_url`.
* A detailed log is written to `<out_dir>/shots.log` on every run.
* If the LLM repeats a previously failed action, it is automatically re-queried with a different approach.
