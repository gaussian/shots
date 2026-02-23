from __future__ import annotations

import logging
import time

from playwright.sync_api import Page

log = logging.getLogger("shots.stability")


def wait_for_network_idle_best_effort(page: Page, timeout_ms: int) -> None:
    """
    Best-effort: some SPAs keep connections open. We attempt networkidle but do not fail hard.
    """
    t0 = time.monotonic()
    try:
        page.wait_for_load_state("networkidle", timeout=timeout_ms)
        log.debug("  network_idle ok (%.1fs)", time.monotonic() - t0)
    except Exception:
        log.debug("  network_idle timed out after %.1fs (best-effort, continuing)", time.monotonic() - t0)


def wait_for_dom_quiet(page: Page, quiet_ms: int = 800, timeout_ms: int = 10_000) -> None:
    """
    Wait until DOM stops mutating for quiet_ms (best effort).
    """
    t0 = time.monotonic()
    try:
        page.evaluate(
            """
            async ({ quietMs, timeoutMs }) => {
              let last = Date.now();
              const obs = new MutationObserver(() => last = Date.now());
              obs.observe(document, { subtree: true, childList: true, attributes: true });
              const start = Date.now();
              while (true) {
                await new Promise(r => setTimeout(r, 100));
                if (Date.now() - last >= quietMs) break;
                if (Date.now() - start > timeoutMs) break;
              }
              obs.disconnect();
            }
            """,
            {"quietMs": quiet_ms, "timeoutMs": timeout_ms},
        )
        log.debug("  dom_quiet ok (%.1fs)", time.monotonic() - t0)
    except Exception:
        log.debug("  dom_quiet failed (%.1fs)", time.monotonic() - t0)


def wait_for_animations(page: Page, timeout_ms: int = 3_000) -> None:
    """
    Wait for CSS animations/transitions to finish (best effort).
    """
    t0 = time.monotonic()
    try:
        page.evaluate(
            """
            async ({ timeoutMs }) => {
              const start = Date.now();
              while (true) {
                const anims = document.getAnimations
                  ? document.getAnimations().filter(a => a.playState === 'running')
                  : [];
                if (anims.length === 0) break;
                if (Date.now() - start > timeoutMs) break;
                await Promise.allSettled(anims.map(a => a.finished.catch(() => null)));
              }
            }
            """,
            {"timeoutMs": timeout_ms},
        )
        log.debug("  animations ok (%.1fs)", time.monotonic() - t0)
    except Exception:
        log.debug("  animations failed (%.1fs)", time.monotonic() - t0)


def wait_for_toasts(page: Page, timeout_ms: int = 4_000) -> None:
    """
    Best-effort wait for ephemeral UI to disappear.
    """
    t0 = time.monotonic()
    try:
        page.wait_for_timeout(300)
        page.evaluate(
            """
            async ({ timeoutMs }) => {
              const start = Date.now();
              while (true) {
                const possible = Array.from(document.querySelectorAll(
                  '[role="alert"], .toast, .snackbar, .notification'
                )).filter(el => el && el.offsetParent !== null);
                if (possible.length === 0) break;
                if (Date.now() - start > timeoutMs) break;
                await new Promise(r => setTimeout(r, 250));
              }
            }
            """,
            {"timeoutMs": timeout_ms},
        )
        log.debug("  toasts ok (%.1fs)", time.monotonic() - t0)
    except Exception:
        log.debug("  toasts failed (%.1fs)", time.monotonic() - t0)


def wait_until_stable(page: Page, timeout_ms: int = 45_000) -> None:
    log.debug("wait_until_stable start")
    t0 = time.monotonic()
    # All caps are aggressive — server-rendered pages need almost no wait.
    wait_for_network_idle_best_effort(page, timeout_ms=min(timeout_ms, 2_000))
    wait_for_dom_quiet(page, quiet_ms=400, timeout_ms=2_000)
    wait_for_animations(page, timeout_ms=1_000)
    wait_for_toasts(page, timeout_ms=1_000)
    page.wait_for_timeout(100)
    log.debug("wait_until_stable done (%.1fs total)", time.monotonic() - t0)
