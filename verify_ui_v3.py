
import asyncio
from playwright.async_api import async_playwright
import os
import subprocess
import time

async def verify():
    # Start the UI
    # Make sure we use the correct module
    proc = subprocess.Popen(
        ["python", "-m", "continum.cli", "ui", "--port", "5052"],
        stdout=open("ui_verify_v3.log", "w"),
        stderr=subprocess.STDOUT
    )

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()

            # Wait for UI to be ready (Gateway)
            max_retries = 60
            ready = False
            for i in range(max_retries):
                try:
                    await page.goto("http://localhost:5052")
                    await page.wait_for_selector(".gw-title", timeout=5000)
                    print("Gateway is ready")
                    ready = True
                    break
                except Exception as e:
                    print(f"Waiting for gateway... ({i+1})")
                    await asyncio.sleep(2)

            if not ready:
                print("UI failed to start")
                return

            # Select Analyst role
            await page.click('.role-card[data-role="analyst"]')
            await page.click('#gw-enter')

            # Wait for App to load
            await page.wait_for_selector(".sb-brand", timeout=10000)
            print("App loaded")

            # 1. Check Right Panel Tabs
            tabs_text = await page.inner_text(".rp-tabs")
            print(f"Tabs found: {tabs_text}")

            expected_tabs = ["Insights", "Narrative", "Ask AI", "Outputs"]
            for tab in expected_tabs:
                if tab in tabs_text:
                    print(f"✅ Tab found: {tab}")
                else:
                    print(f"❌ Tab missing: {tab}")

            if "Evidence" in tabs_text:
                print("❌ Evidence tab still present")
            else:
                print("✅ Evidence tab removed")

            # 2. Check for sidebars
            left_visible = await page.is_visible("#sidebar")
            right_visible = await page.is_visible("#right-panel")
            print(f"Left sidebar visible: {left_visible}, Right sidebar visible: {right_visible}")

            # 3. Test collapsing left sidebar
            await page.click("#sidebar button") # The toggle button
            await asyncio.sleep(1)
            is_collapsed = await page.evaluate("document.getElementById('app').classList.contains('sb-collapsed')")
            print(f"Left sidebar collapsed class present: {is_collapsed}")
            if is_collapsed:
                print("✅ Left sidebar collapsing works")
            else:
                print("❌ Left sidebar collapsing failed")

            # 4. Test collapsing right panel
            await page.click("#right-panel button") # The toggle button
            await asyncio.sleep(1)
            is_rp_collapsed = await page.evaluate("document.getElementById('app').classList.contains('rp-collapsed')")
            print(f"Right panel collapsed class present: {is_rp_collapsed}")
            if is_rp_collapsed:
                print("✅ Right panel collapsing works")
            else:
                print("❌ Right panel collapsing failed")

            # 5. Check Module Click (Console update)
            # Re-expand sidebar if needed
            if is_collapsed: await page.click("#sidebar button")

            await page.click("text=Planning") # Go to planning section
            await page.wait_for_selector("#grid-planning .mod-card")

            # Click a module
            module_name = await page.inner_text("#grid-planning .mod-card .mod-name >> nth=0")
            print(f"Clicking module: {module_name}")
            await page.click("#grid-planning .mod-card >> nth=0")

            # Check console header
            console_label = await page.inner_text("#console-label")
            print(f"Console label after click: {console_label}")
            if module_name in console_label:
                print("✅ Console updated with module name on click")
            else:
                print("❌ Console did not update on click")

            # 6. Check for experiment selection red border (by default none selected)
            border_color = await page.evaluate("getComputedStyle(document.getElementById('exp-select')).borderColor")
            print(f"Experiment selector border color: {border_color}")
            # Note: red border only appears if we try to run without selection, but let's check initial

            # 7. Take a screenshot
            await page.screenshot(path="verification_final.png", full_page=True)
            print("Screenshot saved to verification_final.png")

            await browser.close()
    finally:
        proc.terminate()

if __name__ == "__main__":
    asyncio.run(verify())
