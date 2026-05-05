import asyncio
import json
from playwright.async_api import async_playwright

async def scrape_imdb_top_250():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # Оптимизация: не качаем картинки, чтобы не было таймаута
        async def block_aggressively(route):
            if route.request.resource_type in ["image", "media", "font"]:
                await route.abort()
            else:
                await route.continue_()
        await page.route("**/*", block_aggressively)

        print("Загружаем страницу (с увеличенным таймаутом)...")
        try:
            # Ждем только структуру текста, а не всю тяжелую графику
            await page.goto("https://www.imdb.com/chart/top/", 
                           timeout=60000, 
                           wait_until="domcontentloaded")

            # Ждем, пока прогрузится основной список
            await page.wait_for_selector(".ipc-metadata-list-summary-item", timeout=20000)

            movies_elements = await page.query_selector_all(".ipc-metadata-list-summary-item")
            movies_data = []

            print(f"Найдено элементов: {len(movies_elements)}. Начинаем сбор данных...")

            for movie in movies_elements:
                title_element = await movie.query_selector(".ipc-title__text")
                title = await title_element.inner_text() if title_element else "N/A"

                rating_element = await movie.query_selector('span[data-testid="ratingGroup--container"]')
                rating = await rating_element.inner_text() if rating_element else "N/A"

                # Ссылка на картинку все равно будет в атрибуте src, даже если мы ее заблокировали
                img_element = await movie.query_selector("img.ipc-image")
                img_url = await img_element.get_attribute("src") if img_element else "N/A"

                movies_data.append({
                    "title": title,
                    "rating": rating.strip().split('\n')[0],
                    "image_url": img_url
                })

            with open("imdb_top_250.json", "w", encoding="utf-8") as f:
                json.dump(movies_data, f, ensure_ascii=False, indent=4)

            print(f"Успех! Собрано {len(movies_data)} фильмов.")

        except Exception as e:
            print(f"Ошибка: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(scrape_imdb_top_250())