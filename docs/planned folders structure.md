```text
imdb-ai-pipeline/
│
├── .github/                       # CI/CD configuration
│   └── workflows/                 # GitHub Actions (e.g., test.yml, lint.yml)
│
├── docs/                          # Project showcase and documentation
│   ├── architecture.png           # System design diagram (Excalidraw/Draw.io)
│   └── screenshots/               # Visuals for Upwork (Swagger, Redis Insight, Excel)
│
├── infra/                         # DevOps and Infrastructure as Code
│   ├── docker-compose.yml         # Main orchestrator for local deployment
│   ├── postgres/                  # Database scripts (e.g., init.sql)
│   ├── redis/                     # Custom Redis configs (if needed)
│   └── .env.example               # Environment variables template
│
├── src/                           # Microservices source code
│   │
│   ├── scraper_python/            # Data collection service (Playwright)
│   │   ├── src/                   # App logic (main, parsers, domain models)
│   │   ├── tests/                 # Unit/Integration tests (pytest)
│   │   ├── requirements.txt       # Dependencies (or pyproject.toml)
│   │   └── Dockerfile             # Container definition for the scraper
│   │
│   ├── worker_dotnet/             # Data processing & storage service (.NET 10)
│   │   ├── ImdbWorker.sln         # .NET Solution file
│   │   ├── src/                   # .NET source code projects
│   │   ├── tests/                 # Unit tests (xUnit/NUnit)
│   │   └── Dockerfile             # Multi-stage Docker build for .NET worker
│   │
│   └── api_fastapi/               # AI-Gateway & Data Delivery API
│       ├── src/                   # Endpoints, LLM integration, Excel export
│       ├── tests/                 # API tests
│       ├── requirements.txt       # Dependencies
│       └── Dockerfile             # Container definition for the API
│
├── .gitignore                     # Ignored files (bin/, obj/, venv/, .env, etc.)
└── README.md                      # Project landing page (Setup, Architecture, Benchmarks)
```