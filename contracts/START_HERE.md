# Contract Synchronization Summary

This document provides a high-level overview of how data contracts are synchronized across the IMDB AI Pipeline.

## The Problem

Previously, data contracts were duplicated:
- Python TypedDict in scraper
- Pydantic models in API and AI worker
- C# records in .NET worker
- SQL schema in PostgreSQL

This **caused contract drift** where fields diverged between services.

## The Solution

**Single Source of Truth**: All contracts defined in `contracts/schemas.json`

Then generated/implemented in each language:
- Python: Pydantic models in `contracts/python_contracts.py`
- C#: Records in `src/worker_dotnet/src/ImdbWorker.Service/Contracts.cs`
- Database: Schema in `infra/postgres/init.sql`

## Key Contracts

### MoviePayload
Flow: Scraper → Redis `movies_stream` → .NET Worker → Database

Fields: `imdb_id`, `rank`, `title`, `rating`, `votes`, `image_url`

### AITaskPayload
Flow: API → Redis `ai_stream` → AI Worker

Fields: `id`, `rank`, `title`, `rating` (subset of MoviePayload)

### DatabaseMovie
Complete record with: all MoviePayload fields + `id`, `ai_summary`, `status`, `created_at`, `updated_at`

## Quick Links

- **[README.md](./README.md)** - Detailed contract documentation
- **[INTEGRATION_GUIDE.md](./INTEGRATION_GUIDE.md)** - How to use contracts in code
- **[schemas.json](./schemas.json)** - JSON Schema source of truth
- **[python_contracts.py](./python_contracts.py)** - Python implementations
- **[test_contracts.py](./test_contracts.py)** - Validation tests
- **[CsharpContracts.cs](./CsharpContracts.cs)** - C# reference implementation

## Running Tests

```bash
cd contracts
python -m pytest test_contracts.py -v
```

Ensures all contracts remain synchronized and valid.

## For Developers

When you need to:

1. **Add a field**: Update `schemas.json` first, then all implementations
2. **Debug a validation error**: Run tests with `-vv` flag
3. **Use a contract in code**: Import from `contracts` package (Python) or `ImdbWorker.Contracts` (C#)
4. **Deploy changes**: Run full test suite before pushing

See [INTEGRATION_GUIDE.md](./INTEGRATION_GUIDE.md) for detailed examples.
