"""Drives the real UI (typing + clicking) and saves the report screenshots."""
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent.parent / "figures"
URL = "http://localhost:8765/"


def type_send(page, text):
    page.fill("#input", "")
    page.type("#input", text, delay=8)
    page.keyboard.press("Enter")
    page.wait_for_timeout(500)


def click(page, label):
    page.locator(".quick button", has_text=label).last.click()
    page.wait_for_timeout(450)


def answer_until_done(page, script):
    for a in script:
        if page.locator(".msg.result, .msg.abstain").count():
            break
        click(page, a)


with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
    errors = []

    page = ctx.new_page()
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto(URL)
    page.wait_for_timeout(1200)
    page.screenshot(path=OUT / "ui_0_welcome.png")

    # 1. a typical fever consultation, captured mid-interview
    type_send(page, "I've had a high fever with chills since yesterday and I keep vomiting, but no cough")
    page.screenshot(path=OUT / "ui_1_interview.png")
    # Dengue profile: answer as a dengue patient would
    dengue = {"pain behind the eyes", "joint pain", "muscle pain", "skin rash", "headache", "fatigue",
              "back pain", "loss of appetite", "malaise", "red spots over body", "nausea", "chills", "vomiting", "high fever"}
    for _ in range(9):
        if page.locator(".msg.result, .msg.abstain").count():
            break
        q = page.locator(".msg.question").last.inner_text().split("?")[0].replace("Do you also have ", "").strip()
        click(page, "Yes" if q in dengue else "No")
    page.locator(".msg.result").last.scroll_into_view_if_needed()
    page.wait_for_timeout(600)
    page.screenshot(path=OUT / "ui_2_result.png")

    # 2. warning sign path
    page2 = ctx.new_page()
    page2.goto(URL)
    page2.wait_for_timeout(800)
    type_send(page2, "Sudden chest pain, sweating a lot and I'm short of breath")
    page2.wait_for_timeout(500)
    page2.screenshot(path=OUT / "ui_3_redflag.png")

    # 3. knowledge question + lay language with typos and negation
    page3 = ctx.new_page()
    page3.goto(URL)
    page3.wait_for_timeout(800)
    type_send(page3, "what is malaria?")
    type_send(page3, "my skin is itchy with a rash and some blistres, no fever")
    page3.wait_for_timeout(500)
    page3.screenshot(path=OUT / "ui_4_info_nlu.png")

    # 4. phone width
    m = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=3)
    pm = m.new_page()
    pm.goto(URL)
    pm.wait_for_timeout(800)
    type_send(pm, "stomach ache and loose motions, not vomiting")
    pm.screenshot(path=OUT / "ui_5_mobile.png")
    overflow = pm.evaluate("document.documentElement.scrollWidth > window.innerWidth")
    print("console errors:", errors, "| mobile horizontal overflow:", overflow)
    b.close()
