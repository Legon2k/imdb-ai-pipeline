# Data Contract Integration Guide

## Quick Start

### For Python Services (Scraper, API, AI Worker)

```python
# Import contracts
from contracts import MoviePayload, AITaskPayload, DatabaseMovie

# Validate incoming data
try:
    movie = MoviePayload.model_validate_json(redis_payload)
except ValidationError as e:
    logger.error(f"Contract violation: {e}")

# Create structured data
task = AITaskPayload(
    id=movie_id,
    rank=1,
    title="The Shawshank Redemption",
    rating=9.3
)

# Serialize to JSON
json_payload = task.model_dump_json()
```

### For C# Services (.NET Worker)

```csharp
// Using contracts from ImdbWorker.Contracts namespace
using ImdbWorker.Contracts;

// Deserialize from Redis
var movie = JsonSerializer.Deserialize<MoviePayload>(json_payload);

// Validate
movie.Validate();

// Use in database operations
await SaveMovieAsync(movie);
```

---

## Architecture

```
┌─────────────────────────────────┐
│   Scraper (Python)              │
│   Publishes MoviePayload        │
└──────────────┬──────────────────┘
               │ JSON
               ▼
        ┌──────────────┐
        │ Redis Stream │ (movies_stream)
        │ movies_stream│
        └──────────────┘
               │
               ▼
    ┌──────────────────────┐
    │  .NET Worker         │
    │  Consumes MoviePayload
    │  Validates & Saves   │
    └──────┬───────────────┘
           │
           ▼
    ┌──────────────────┐
    │  PostgreSQL      │
    │  Database        │
    └──────────────────┘
           ▲
           │
    ┌──────┴──────────┐
    │                 │
    │  FastAPI        │  Reads database, creates AITaskPayload
    │  /movies        │  /enrich endpoint
    │
    └──────┬──────────┘
           │ AITaskPayload JSON
           ▼
    ┌──────────────────┐
    │ Redis Stream     │
    │ ai_stream        │
    └──────────────────┘
           │
           ▼
    ┌──────────────────┐
    │ AI Worker        │
    │ (Python)         │
    │ Consumes Tasks   │
    │ Generates Summaries
    └──────────────────┘
```

---

## Service Mapping

### Scraper → Redis (movies_stream)

**Service**: `src/scraper_python/`

**Contract**: `MoviePayload`

**Fields Produced**:
```json
{
  "imdb_id": "tt0111161",
  "rank": 1,
  "title": "The Shawshank Redemption",
  "rating": 9.3,
  "votes": "2,500,000",
  "image_url": "https://..."
}
```

**Validation**:
- Uses shared contract via `python_contracts.py`
- Validation happens in `scraper.py:extract_movies()`
- Extra fields (`votes_count`, `imdb_url`) are stripped before publishing

---

### .NET Worker: Redis (movies_stream) → PostgreSQL

**Service**: `src/worker_dotnet/src/ImdbWorker.Service/`

**Contract**: `MoviePayload` (from `Contracts.cs`)

**Operations**:
1. Deserialize JSON from Redis stream
2. Validate contract constraints
3. UPSERT into `movies` table with status='pending'

**SQL**:
```sql
INSERT INTO movies (imdb_id, rank, title, rating, votes, image_url, status)
VALUES (@ImdbId, @Rank, @Title, @Rating, @Votes, @ImageUrl, 'pending')
ON CONFLICT (imdb_id) DO UPDATE ...
```

---

### FastAPI: Database → Redis (ai_stream)

**Service**: `src/api_fastapi/src/`

**Contracts**:
- Reads: `DatabaseMovie` (from shared contracts)
- Publishes: `AITaskPayload` (from shared contracts)

**Endpoint**: `POST /movies/enrich?limit=5`

**Flow**:
```python
# 1. Query database for pending movies
pending = await db.fetch("""
    SELECT id, rank, title, rating FROM movies 
    WHERE status = 'pending' LIMIT $1
""", limit)

# 2. Create AI tasks
tasks = [
    {
        "payload": json.dumps(
            AITaskPayload(
                id=m["id"],
                rank=m["rank"],
                title=m["title"],
                rating=float(m["rating"])
            ).model_dump_json()
        )
    }
    for m in pending
]

# 3. Publish to Redis stream
for task in tasks:
    redis.xadd("ai_stream", task)
```

---

### AI Worker: Redis (ai_stream) → PostgreSQL

**Service**: `src/worker_ai_python/src/`

**Contract**: `AITaskPayload` (from shared contracts)

**Validation**:
```python
try:
    task = AITaskPayload.model_validate_json(message)
except ValidationError as e:
    logger.warning(f"Contract violation: {e}")
    # Skip invalid message
    continue
```

**Operations**:
1. Validate incoming task against contract
2. Call LLM API with `title` and `rating`
3. Update database with `ai_summary` and status='completed'

---

## Contract Testing

Run tests to ensure contracts stay synchronized:

```bash
cd contracts
python -m pytest test_contracts.py -v --tb=short
```

**Test Categories**:

1. **Schema Sync** - Pydantic models match JSON schema
2. **MoviePayload Tests** - All validation rules enforced
3. **AITaskPayload Tests** - Required fields and types
4. **DatabaseMovie Tests** - Status enum, optional fields
5. **Cross-Contract** - Hierarchy validation (subset/superset)

**Expected Output**:
```
test_contracts.py::ContractSchemaSyncTest::test_movie_payload_schema_exists PASSED
test_contracts.py::MoviePayloadValidationTest::test_valid_movie_payload_minimal PASSED
test_contracts.py::MoviePayloadValidationTest::test_invalid_imdb_id_format PASSED
...
======================== XX passed in X.XXs ========================
```

---

## Debugging Contract Issues

### Error: `ValidationError: Field required`

**Symptom**: "field required (type=value_error.missing)"

**Cause**: Producer didn't include required field

**Debug**:
```python
# Add logging to producer
logger.info(f"Payload keys: {payload.keys()}")
logger.info(f"Payload: {json.dumps(payload, indent=2)}")
```

**Fix**: Ensure all required fields are populated:
- `imdb_id`: Extract correctly
- `rank`: Sequential 1-250
- `title`: From DOM
- `rating`: Parse correctly
- `votes`: Format as string

---

### Error: `ValidationError: ensure this value has at most 255 characters`

**Symptom**: Title exceeds 255 characters

**Cause**: Movie title is too long

**Debug**:
```python
if len(movie["title"]) > 255:
    logger.warning(f"Title too long ({len(movie['title'])} chars): {movie['title'][:50]}...")
    movie["title"] = movie["title"][:255]  # Truncate
```

---

### Error: `JsonException: invalid payload format`

**Symptom**: C# deserialization fails

**Cause**: JSON structure doesn't match contract

**Debug in C#**:
```csharp
try
{
    var movie = JsonSerializer.Deserialize<MoviePayload>(json);
}
catch (JsonException ex)
{
    logger.LogError($"Failed to deserialize: {ex.Message}");
    logger.LogError($"JSON: {json}");
}
```

**Common Issues**:
- Field name mismatch (`image_url` vs `imageUrl`)
- Type mismatch (`"9.3"` string vs `9.3` number)
- Missing quotes around values

---

## Deployment Checklist

Before deploying contract changes:

- [ ] Updated `contracts/schemas.json`
- [ ] Updated `contracts/python_contracts.py` Pydantic models
- [ ] Updated `src/worker_dotnet/src/ImdbWorker.Service/Contracts.cs`
- [ ] All contract tests pass: `pytest contracts/test_contracts.py`
- [ ] Updated database schema (if adding/removing columns)
- [ ] Updated all services consuming contracts
- [ ] Tested end-to-end with sample data
- [ ] Verified Swagger UI reflects new schema
- [ ] Backward compatibility considered (for optional fields)

---

## FAQ

**Q: Can I add a field to MoviePayload without breaking existing consumers?**

A: Yes, if it's optional. Add to schema with `"required": []`, make it `Optional[T]` in Python, `T?` in C#.

**Q: Where do I make contract changes?**

A: Always start with `contracts/schemas.json` (JSON Schema), then update language implementations.

**Q: Do I need to update all 3 representations (JSON, Python, C#)?**

A: Yes. The whole point is keeping them in sync.

**Q: What if C# and Python field names differ?**

A: Use `[JsonPropertyName("field_name")]` in C# to map to canonical JSON field name.

**Q: How do I handle missing fields during migration?**

A: Make field optional, populate existing records, then make required in new code.

---

## Related Files

- `contracts/schemas.json` - JSON Schema (source of truth)
- `contracts/python_contracts.py` - Python Pydantic models
- `contracts/__init__.py` - Python package exports
- `contracts/test_contracts.py` - Validation tests
- `contracts/README.md` - Detailed documentation
- `src/worker_dotnet/src/ImdbWorker.Service/Contracts.cs` - C# records
- `infra/postgres/init.sql` - Database schema
