from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    console_errors = []
    page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: console_errors.append(str(error)))
    page.goto("http://127.0.0.1:5173/admin/", wait_until="networkidle")
    print("initial_title", page.locator("h1").first.inner_text())
    print("map_paths", page.locator(".gov-path").count())
    page.locator(".gov-path").first.click()
    page.wait_for_timeout(500)
    print("region_panel", page.locator(".region-detections").count())
    page.get_by_text("Découvrir", exact=True).first.click()
    page.wait_for_timeout(500)
    print("kanban_cards", page.locator(".kanban-card").count())
    if page.locator(".kanban-card").count():
        page.locator(".kanban-card").first.click()
        page.wait_for_timeout(500)
        print("drawer", page.locator(".drawer-panel").count())
        print("drawer_has_raw_id", "ENT-" in page.locator(".drawer-panel").inner_text())
    page.screenshot(path="ui-check.png", full_page=True)
    print("console_errors", console_errors)
    browser.close()
