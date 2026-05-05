import asyncio
import json
from playwright.async_api import async_playwright

async def scrape_imdb_top_250():
    async with async_playwright() as p:
        # Запускаем браузер
        browser = await p.chromium.launch(headless=True)
        # Настраиваем контекст с обычным User-Agent, чтобы IMDb нас не забанил
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        print("Загружаем страницу...")
        await page.goto("https://www.imdb.com/chart/top/")

        # IMDb подгружает список динамически, подождем появления элементов
        await page.wait_for_selector(".ipc-metadata-list-summary-item")

        # Находим все карточки фильмов
        movies_elements = await page.query_selector_all(".ipc-metadata-list-summary-item")
        
        movies_data = []

        for movie in movies_elements:
            # Извлекаем название
            title_element = await movie.query_selector(".ipc-title__text")
            title = await title_element.inner_text() if title_element else "N/A"

            # Извлекаем рейтинг
            rating_element = await movie.query_selector('span[data-testid="ratingGroup--container"]')
            rating = await rating_element.inner_text() if rating_element else "N/A"

            # Извлекаем URL картинки
            img_element = await movie.query_selector("img.ipc-image")
            img_url = await img_element.get_attribute("src") if img_element else "N/A"

            movies_data.append({
                "title": title,
                "rating": rating.strip().split('\n')[0], # Очищаем от лишних символов
                "image_url": img_url
            })

        # Сохраняем в JSON
        with open("imdb_top_250.json", "w", encoding="utf-16") as f:
            json.dump(movies_data, f, ensure_ascii=False, indent=4)

        print(f"Готово! Собрано фильмов: {len(movies_data)}")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(scrape_imdb_top_250())
