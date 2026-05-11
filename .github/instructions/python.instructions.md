---
description: "Use when editing Python files in the IMDb scraper project, ensuring best practices for web scraping, data handling, and validation."
applyTo: "**/*.py"
---

# Python Coding Guidelines for IMDb Scraper

- Follow PEP 8 style guidelines for code formatting.
- Use type hints for function parameters and return values.
- Handle exceptions properly, especially for network requests (timeouts, HTTP errors).
- Validate scraped data against the provided JSON schemas before saving.
- Use logging instead of print statements for debugging and monitoring.
- Avoid hardcoding URLs or sensitive data; use constants or environment variables.
- Write unit tests for critical functions, especially parsing and validation logic.
- Document functions with docstrings explaining purpose, parameters, and return values.