# Data Contract Synchronization Strategy

## Problem Statement

Previously, data contracts were duplicated across multiple services:
- Python TypedDict (Scraper)
- Pydantic models (AI Worker, API)
- C# records (.NET Worker)
- SQL schema (PostgreSQL)

This caused **contract drift** where fields would diverge between services, leading to serialization errors and data loss at service boundaries.

## Solution: Single Source of Truth

All data contracts are now centralized in `/contracts/` directory with multiple representations for each language/format.

```
contracts/
├── schemas.json              # JSON Schema (language-agnostic, v7)
├── python_contracts.py       # Pydantic models + TypedDict
├── CsharpContracts.cs        # C# records with validation
├── test_contracts.py         # Contract sync validation tests
├── __init__.py              # Python package
└── README.md                # This file
```

## Contract Hierarchy

```
┌─────────────────────────────────────────┐
│     schemas.json (JSON Schema)           │  ← Single Source of Truth
│  (Language-agnostic, machine-readable)   │
└──────────────────────┬──────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ▼              ▼              ▼
   Python Pydantic   C# Records   Database Schema
    (runtime valid)  (compile-time) (persistence)
```

## Contracts Overview

### 1. MoviePayload

**Purpose**: Core movie data flowing through Scraper → Redis → Database

**Used By**:
- Scraper: publishes to `movies_stream` (Redis)
- .NET Worker: deserializes from Redis stream
- Database: persists in `movies` table

**Fields**:
```python
{
    "imdb_id": str,       # Pattern: ^tt\d+$ (e.g., "tt0111161")
    "rank": int,          # Range: 1-250
    "title": str,         # Length: 1-255
    "rating": float,      # Range: 0.0-10.0
    "votes": str,         # Formatted string (e.g., "2,500,000")
    "image_url": str?     # Optional URL
}
```

**Validation Rules**:
- `imdb_id`: Must match IMDB format (tt + digits)
- `rank`: Must be 1-250 (IMDB Top 250 only)
- `title`: Required, 1-255 characters
- `rating`: Must be 0-10 decimal
- `votes`: Required non-empty string
- `image_url`: Optional, can be null

---

### 2. AITaskPayload

**Purpose**: Specialized subset for AI enrichment tasks

**Used By**:
- FastAPI: creates from database records
- Redis `ai_stream`: transport layer
- AI Worker: validates and processes

**Fields**:
```python
{
    "id": int,       # Database movie ID (surrogate key)
    "rank": int,     # Range: 1-250
    "title": str,    # Length: 1-255
    "rating": float  # Range: 0.0-10.0
}
```

**Why smaller?**
- LLM worker only needs context for prompt generation
- Reduces Redis stream payload size
- Explicit about what AI tasks contain

---

### 3. DatabaseMovie

**Purpose**: Complete movie record as stored in PostgreSQL

**Used By**:
- FastAPI: response model for GET /movies
- Tests: database validation
- Serialization to JSON/export

**Fields**:
```python
{
    "id": int,                          # Primary key
    "imdb_id": str,                     # IMDB identifier
    "rank": int,                        # 1-250
    "title": str,                       # Movie name
    "rating": float,                    # 0-10
    "votes": str,                       # Vote count
    "image_url": str?,                  # Poster URL
    "ai_summary": str?,                 # AI-generated text
    "status": str,                      # pending|processing|completed|failed
    "created_at": datetime,             # ISO 8601 timestamp
    "updated_at": datetime              # ISO 8601 timestamp
}
```

---

## Implementation Guide

### Python (Scraper, API, AI Worker)

**Import and Use**:
```python
from contracts import MoviePayload, AITaskPayload

# Validate incoming JSON
movie_data = MoviePayload.model_validate_json(redis_message)

# Create structured data
task = AITaskPayload(id=1, rank=1, title="Test", rating=9.0)

# Serialize for transmission
json_str = task.model_dump_json()

# Type hints
def process_movie(movie: MoviePayload) -> None:
    print(f"Processing {movie.title}")
```

**Pydantic Features**:
- Automatic validation
- Type checking
- JSON schema generation (Swagger UI)
- Serialization/deserialization
- Comprehensive error messages

---

### C# (.NET Worker)

**Import and Use**:
```csharp
using ImdbWorker.Contracts;

// Deserialize from Redis
var options = new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase };
var movie = JsonSerializer.Deserialize<MoviePayload>(json, options);

// Validate
movie.Validate();

// Use in database operations
await SaveMovieAsync(movie);
```

**JSON Property Names**:
- C# uses `[JsonPropertyName]` to map snake_case JSON to PascalCase C#
- Both `movie.ImdbId` (C#) and `"imdb_id"` (JSON) refer to the same field

---

### Database Schema

**Synchronization**:
```sql
-- Maps to DatabaseMovie contract
CREATE TABLE movies (
    id SERIAL PRIMARY KEY,
    imdb_id VARCHAR(50) UNIQUE NOT NULL,
    rank INTEGER,
    title VARCHAR(255) NOT NULL,
    rating NUMERIC(3, 1),
    votes VARCHAR(50),
    image_url TEXT,
    ai_summary TEXT,
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

**Schema Validation**:
- Field names, types, and constraints match `contracts/schemas.json`
- Nullable fields in schema map to nullable columns (`NULL` in SQL)
- `status` enum values: `pending`, `processing`, `completed`, `failed`

---

## Contract Testing

Run contract validation tests to catch drift:

```bash
# Python
cd contracts
python -m pytest test_contracts.py -v

# Or with coverage
python -m pytest test_contracts.py --cov=python_contracts --cov-report=term-plus
```

**Test Categories**:

1. **Schema Sync Tests**: Verify Pydantic models match JSON schema
2. **MoviePayload Tests**: Validate all rules (imdb_id format, rank bounds, etc.)
3. **AITaskPayload Tests**: Validate required fields and types
4. **DatabaseMovie Tests**: Validate status enum and optional fields
5. **Cross-Contract Tests**: Verify contract hierarchy (AITask ⊆ MoviePayload ⊆ DatabaseMovie)

---

## Adding New Fields

**If you need to add a field to all contracts:**

1. **Update `contracts/schemas.json`**:
   ```json
   {
     "definitions": {
       "MoviePayload": {
         "properties": {
           "new_field": {
             "type": "string",
             "description": "..."
           }
         },
         "required": ["...", "new_field"]
       }
     }
   }
   ```

2. **Update `contracts/python_contracts.py`**:
   ```python
   class MoviePayload(BaseModel):
       new_field: str = Field(..., description="...")
   ```

3. **Update `contracts/CsharpContracts.cs`**:
   ```csharp
   public record MoviePayload(
       ...existing fields...,
       [property: JsonPropertyName("new_field")]
       string NewField
   );
   ```

4. **Update database schema** (`infra/postgres/init.sql`):
   ```sql
   ALTER TABLE movies ADD COLUMN new_field TEXT;
   ```

5. **Run contract tests**:
   ```bash
   python -m pytest contracts/test_contracts.py -v
   ```

6. **Update consuming services**:
   - Scraper: populate the field
   - Workers: handle the field
   - API: expose in responses

---

## Deployment Checklist

Before deploying changes to contracts:

- [ ] Updated `contracts/schemas.json` with new/changed fields
- [ ] Updated Pydantic models in `python_contracts.py`
- [ ] Updated C# records in `CsharpContracts.cs`
- [ ] All contract tests pass: `pytest contracts/test_contracts.py`
- [ ] Database migration created (if schema changed)
- [ ] All services updated to handle new fields
- [ ] Backward compatibility considered (nullable fields for optional additions)
- [ ] Swagger UI regenerated (run FastAPI)
- [ ] Integration tests pass end-to-end

---

## Troubleshooting

**Error: `ValidationError: Field required`**
- Field missing from JSON payload
- Check that producer sends all required fields
- Verify schema definition has `"required": [...]`

**Error: `JsonPropertyName mismatch`**
- C# property name doesn't match JSON field name
- Example: C# `ImdbId` must have `[JsonPropertyName("imdb_id")]`

**Error: Contract tests fail**
- Run: `python -m pytest contracts/test_contracts.py -vv`
- Check which contract definition diverged
- Update the diverged contract to match schema

**Error: Database INSERT fails**
- SQL column type/constraint doesn't match schema
- Example: `rating` must be `NUMERIC(3,1)`, not `INTEGER`
- Update `infra/postgres/init.sql` and create migration

---

## FAQ

**Q: Can I add optional fields without breaking consumers?**
A: Yes. Use `Optional[T]` in Python and `T?` in C#, keep the field out of `required` in JSON Schema.

**Q: Do I need to update all three representations (JSON Schema, Python, C#)?**
A: Yes. The whole point is keeping them in sync. Automated tooling (in future) may generate code from schema.

**Q: What if I want different field names in Python vs C#?**
A: Use `JsonPropertyName` in C# to map to the canonical name in JSON schema. Example:
```csharp
[property: JsonPropertyName("image_url")]
string ImageUrl
```

**Q: How do I version contracts?**
A: Keep current contracts for backward compatibility. Add new `v2` definitions to schema if breaking changes needed. Add feature flags in code for migration period.

**Q: Can I make a field required that was previously optional?**
A: Only if you have a migration plan:
  1. Add the field as optional
  2. Populate all existing records
  3. Make it required in new code
  4. Phase out old code

---

## Related Files

- [schemas.json](./schemas.json) - JSON Schema definitions
- [python_contracts.py](./python_contracts.py) - Python Pydantic models
- [CsharpContracts.cs](./CsharpContracts.cs) - C# records
- [test_contracts.py](./test_contracts.py) - Validation tests
- [infra/postgres/init.sql](../infra/postgres/init.sql) - Database schema
