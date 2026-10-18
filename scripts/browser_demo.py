"""Record the working browser flow in the app's explicitly displayed agent mode.

The UI and filename distinguish live Gemini from deterministic rehearsal.
Set CHROMIUM_EXECUTABLE if Playwright's bundled browser is unavailable.
"""

import asyncio
import os
import subprocess
from pathlib import Path
from playwright.async_api import async_playwright


async def main():
    artifacts = Path("artifacts")
    artifacts.mkdir(exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=os.environ.get("CHROMIUM_EXECUTABLE") or None
        )
        context = await browser.new_context(
            viewport={"width": 1512, "height": 1100},
            device_scale_factor=1,
            record_video_dir=str(artifacts),
            record_video_size={"width": 1512, "height": 1100},
            reduced_motion="reduce",
        )
        page = await context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        base = os.environ.get("APP_URL", "http://127.0.0.1:8000")
        await page.goto(base)
        await page.wait_for_selector("h1")
        cfg = await (await page.request.get(base + "/api/config")).json()
        if not cfg.get("can_control", True):
            activation = await page.request.post(
                base + f"/api/workspaces/{cfg['tenant_id']}/activate", data={}
            )
            if not activation.ok:
                raise RuntimeError(
                    "Cannot activate the selected workspace while recording"
                )
            await page.reload()
        if cfg.get("active_run"):
            response = await page.request.post(
                base + f"/api/runs/{cfg['active_run']}/reset", data={}
            )
            if not response.ok:
                raise RuntimeError("Cannot reset the active run while recording")
            await page.reload()
        await page.get_by_role("button", name="Initialize company").click()
        await page.get_by_role("button", name="Inject fault", exact=True).wait_for()
        await page.wait_for_timeout(2500)
        await page.screenshot(path=str(artifacts / "01-healthy.png"), full_page=True)
        await page.get_by_role("button", name="Inject fault", exact=True).click()
        await page.wait_for_timeout(2000)
        await page.get_by_role("button", name="Investigate", exact=True).click()
        await page.get_by_role("button", name="Apply verified repair").wait_for(
            timeout=210000
        )
        await page.wait_for_timeout(1500)
        await page.screenshot(
            path=str(artifacts / "02-three-futures.png"), full_page=True
        )
        await page.get_by_role("button", name="Inspect evidence").nth(1).click()
        await page.get_by_role("heading", name="Actual process changes").wait_for()
        await page.wait_for_timeout(2000)
        await page.screenshot(path=str(artifacts / "03-evidence.png"), full_page=True)
        await page.get_by_role("button", name="Close evidence").click()
        await page.get_by_role("button", name="Apply verified repair").click()
        await page.get_by_role(
            "heading", name="Checkout recovered. Procedure saved."
        ).wait_for()
        await page.wait_for_timeout(2000)
        await page.screenshot(path=str(artifacts / "04-recovered.png"), full_page=True)
        await page.get_by_role("button", name="View incident memory").click()
        await page.get_by_role(
            "heading", name="Enable graceful fallback", exact=True
        ).first.wait_for()
        await page.wait_for_timeout(2000)
        await page.screenshot(path=str(artifacts / "05-memory.png"), full_page=True)
        if os.environ.get("RESTART_CONTROLLER") == "1":
            await asyncio.to_thread(
                subprocess.run,
                ["docker", "compose", "restart", "api"],
                check=True,
                capture_output=True,
            )
            for _ in range(40):
                try:
                    health = await page.request.get(base + "/api/health")
                    if health.ok:
                        break
                except Exception:
                    pass
                await page.wait_for_timeout(500)
            await page.reload()
            await page.get_by_role(
                "heading", name="Checkout recovered. Procedure saved."
            ).wait_for()
            await page.get_by_role("button", name="View incident memory").click()
            await page.get_by_role(
                "heading", name="Enable graceful fallback", exact=True
            ).first.wait_for()
            await page.screenshot(
                path=str(artifacts / "05b-controller-restored.png"), full_page=True
            )
        await page.get_by_role("button", name="Incident command", exact=True).click()
        await page.get_by_role("checkbox", name="Mandatory recommendations").click()
        await page.get_by_role("button", name="Inject again", exact=True).click()
        await page.wait_for_timeout(1200)
        await page.get_by_role("button", name="Investigate", exact=True).click()
        await page.get_by_role(
            "heading", name="No repair satisfies the current requirements"
        ).wait_for(timeout=210000)
        await page.wait_for_timeout(2000)
        await page.screenshot(
            path=str(artifacts / "06-policy-revalidated.png"), full_page=True
        )
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.wait_for_timeout(500)
        await page.evaluate("window.scrollTo(0, 0)")
        await page.screenshot(path=str(artifacts / "07-mobile.png"))
        assert await page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth"
        ), "Mobile horizontal overflow"
        assert not errors, errors
        video = page.video
        await context.close()
        if video:
            filename = (
                "aftershock-live-demo.webm"
                if cfg["mode"] == "live"
                else "aftershock-rehearsal-demo.webm"
            )
            await video.save_as(str(artifacts / filename))
        await browser.close()
        print("Browser flow passed; screenshots and video saved in artifacts/.")


if __name__ == "__main__":
    asyncio.run(main())
