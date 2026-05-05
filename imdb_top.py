import asyncio
import json
from playwright.async_api import async_playwright

async def scrape_imdb_top_250():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        context = await browser.new_context(
            user_agent="Mozilla/5.0"
        )

        page = await context.new_page()

        # Блокируем тяжёлые ресурсы
        await page.route("**/*", lambda route: (
            route.abort() if route.request.resource_type in ["image", "media", "font"]
            else route.continue_()
        ))

        await page.goto(
            "https://www.imdb.com/chart/top/",
            wait_until="domcontentloaded"
        )

        # 💡 Ждём, пока появятся ВСЕ 250 элементов
        await page.wait_for_function(
            "() => document.querySelectorAll('.ipc-metadata-list-summary-item').length >= 250",
            timeout=30000
        )

        movies = page.locator(".ipc-metadata-list-summary-item")
        count = await movies.count()

        print(f"Элементов: {count}")

        results = []

        for i in range(count):
            movie = movies.nth(i)

            title = await movie.locator(".ipc-title__text").inner_text()

            rating = await movie.locator(
                "span[aria-label*='rating']"
            ).inner_text()

            img = await movie.locator("img").get_attribute("src")

            results.append({
                "title": title,
                "rating": rating,
                "image_url": img
            })

        with open("imdb_top_250.json", "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        print("Готово!")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(scrape_imdb_top_250())