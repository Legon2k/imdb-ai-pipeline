# Deployment Guide: Data Contract Synchronization

**Last Updated**: May 16, 2026  
**Status**: Ready for deployment  
**Testing**: ✓ All contracts validated

## Overview

This deployment introduces **centralized data contracts** to eliminate schema drift across the IMDB AI Pipeline. All data structures (Python TypedDict, Pydantic models, C# records, SQL schema) now derive from a single JSON Schema source of truth.

## What Changed

### New Files Created

1. **`contracts/schemas.json`** - JSON Schema definitions for all data structures (MoviePayload, AITaskPayload, DatabaseMovie)
2. **`contracts/python_contracts.py`** - Pydantic models for Python services
3. **`contracts/__init__.py`** - Python package exports
4. **`contracts/test_contracts.py`** - Comprehensive validation tests
5. **`contracts/CsharpContracts.cs`** - C# record implementations  
6. **`contracts/README.md`** - Detailed contract documentation
7. **`contracts/INTEGRATION_GUIDE.md`** - How to use contracts in code
8. **`contracts/START_HERE.md`** - Quick start guide
9. **`src/worker_dotnet/src/ImdbWorker.Service/Contracts.cs`** - C# contract classes

### Modified Files

1. **`src/worker_ai_python/src/main.py`**
   - Imports `AITaskPayload` from shared contracts
   - Replaces local `AITaskContract` class
   - Uses contract from `contracts` package

2. **`src/api_fastapi/src/main.py`**
   - Imports `MoviePayload`, `AITaskPayload`, `DatabaseMovie` from contracts
   - Uses `DatabaseMovie` as base for `MovieResponse`
   - Enables consistency with database schema

3. **`src/worker_dotnet/src/ImdbWorker.Service/Worker.cs`**
   - Imports `MoviePayload` from `ImdbWorker.Contracts` namespace
   - Adds validation call: `movie.Validate()`
   - Uses centralized contract definitions

4. **`src/scraper_python/src/imdb_top250_scraper/models.py`**
   - Imports `MoviePayload` from shared contracts
   - Aliases as `Movie` for backward compatibility
   - Ensures scraper output matches contract

5. **`src/scraper_python/src/imdb_top250_scraper/validation.py`**
   - Uses Pydantic validation from shared `MoviePayload`
   - Replaces manual field checking
   - Validates against contract constraints

6. **`src/scraper_python/src/imdb_top250_scraper/scraper.py`**
   - Maps extracted data to `MoviePayload` contract fields
   - Removes extra fields (`votes_count`, `imdb_url`)
   - Only publishes canonical fields to Redis

## Deployment Steps

### Phase 1: Prepare (Pre-deployment)

1. **Code Review**
   ```bash
   # Review contract definitions
   cat contracts/schemas.json | jq '.definitions'
   
   # Verify Python implementations
   python -c "from contracts import MoviePayload, AITaskPayload, DatabaseMovie; print('✓ All contracts importable')"
   
   # Build C# project
   cd src/worker_dotnet && dotnet build
   ```

2. **Run Contract Tests**
   ```bash
   cd contracts
   python -m pytest test_contracts.py -v
   # All tests should pass
   ```

3. **Verify Backward Compatibility**
   - Existing database schema unchanged
   - All fields remain the same
   - No data migration required

### Phase 2: Deploy

#### Step 1: Deploy Python Services

Deploy in this order to avoid contract violations:

**1.1 Deploy Scraper**
```bash
# Rebuild and push scraper image
docker build -t imdb-scraper:latest ./src/scraper_python
docker push imdb-scraper:latest

# Restart scraper (will use new contracts)
docker compose up -d scraper
```

**Verification**:
```bash
# Check scraper logs
docker compose logs scraper | grep -i "published\|error"

# Verify Redis stream contains valid payloads
redis-cli XRANGE movies_stream - + | head -10
```

**1.2 Deploy AI Worker**
```bash
# Rebuild and push AI worker image
docker build -t imdb-ai-worker:latest ./src/worker_ai_python
docker push imdb-ai-worker:latest

# Restart AI worker
docker compose up -d worker_ai
```

**Verification**:
```bash
# Check AI worker logs for contract validation
docker compose logs worker_ai | grep -i "contract_violation\|task_completed"

# Verify AI tasks are processed
redis-cli XINFO STREAM ai_stream
```

**1.3 Deploy FastAPI**
```bash
# Rebuild and push API image
docker build -t imdb-api:latest ./src/api_fastapi
docker push imdb-api:latest

# Restart API
docker compose up -d api
```

**Verification**:
```bash
# Check API starts successfully
curl -s http://localhost:8000/health | jq .
curl -s http://localhost:8000/ready | jq .

# Verify Swagger schema is updated
curl -s http://localhost:8000/openapi.json | jq '.components.schemas' | head -30
```

#### Step 2: Deploy .NET Worker

```bash
# Rebuild with new contracts
cd src/worker_dotnet
dotnet publish -c Release

# Stop old container
docker compose down worker_dotnet

# Rebuild and push image
docker build -t imdb-worker:latest ./src/worker_dotnet
docker push imdb-worker:latest

# Restart with new code
docker compose up -d worker_dotnet
```

**Verification**:
```bash
# Check .NET worker logs
docker compose logs worker_dotnet | grep -i "saved\|error" | tail -20

# Verify movies are being saved
docker compose exec postgres psql -U imdb_admin -d imdb_ai_db -c \
  "SELECT COUNT(*) as total, status, COUNT(*) FILTER (WHERE updated_at > NOW() - INTERVAL '5 minutes') as recent FROM movies GROUP BY status;"
```

### Phase 3: Validation (Post-deployment)

1. **End-to-End Test**
   ```bash
   # 1. Trigger scraper
   docker compose exec scraper python -m imdb_top.py --limit=5
   
   # 2. Verify movies in Redis
   redis-cli XLEN movies_stream  # Should increase
   
   # 3. Check .NET worker processed them
   docker compose logs worker_dotnet | grep "Saved to DB"
   
   # 4. Query API
   curl -s http://localhost:8000/movies | jq '.[0]'
   
   # 5. Trigger AI enrichment
   curl -X POST http://localhost:8000/movies/enrich?limit=2
   
   # 6. Verify AI worker processed tasks
   docker compose logs worker_ai | grep "task_completed"
   
   # 7. Check database for summaries
   docker compose exec postgres psql -U imdb_admin -d imdb_ai_db -c \
     "SELECT title, status, ai_summary FROM movies WHERE ai_summary IS NOT NULL LIMIT 2;"
   ```

2. **Health Checks**
   ```bash
   # All services should report healthy status
   docker compose ps
   
   # Check for error logs
   docker compose logs --tail=50 | grep -i error
   
   # Verify database connections
   docker compose exec postgres psql -U imdb_admin -d imdb_ai_db -c "SELECT 1;"
   docker compose exec redis redis-cli PING
   ```

3. **Contract Validation**
   ```bash
   # Run validation tests in production environment
   docker compose exec api python -m pytest /app/contracts/test_contracts.py -v
   ```

## Rollback Plan

If issues occur, follow this procedure:

### Quick Rollback (< 10 minutes)

1. **Restore Docker Images**
   ```bash
   # Use previous tags
   docker pull imdb-scraper:v3.0.0
   docker pull imdb-api:v3.0.0
   docker pull imdb-worker:v3.0.0
   docker pull imdb-ai-worker:v3.0.0
   
   # Update docker-compose.yml to use old image tags
   # Then restart services
   docker compose down
   docker compose up -d
   ```

2. **Verify Rollback**
   ```bash
   # Check all services are back online
   docker compose ps
   curl http://localhost:8000/health
   ```

### Git Rollback (if needed)

```bash
# Revert to previous commit
git revert HEAD
git push origin main

# Redeploy from previous commit
docker compose down
git pull
docker-compose build
docker-compose up -d
```

## Known Issues & Mitigations

### Issue 1: Import Path Errors

**Symptom**: `ModuleNotFoundError: No module named 'contracts'`

**Cause**: Python services not finding the `contracts` package

**Mitigation**:
```python
# Ensure sys.path is set correctly in each service
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../'))
from contracts import MoviePayload
```

**Resolution**: Verify PYTHONPATH includes project root in Docker images.

### Issue 2: Contract Validation Failures

**Symptom**: `ValidationError: ensure this value is a valid integer`

**Cause**: Data type mismatch (e.g., string instead of int)

**Mitigation**: Check logs for exact field and value:
```bash
docker compose logs | grep "ValidationError\|contract_violation"
```

**Resolution**: Update producer to match contract schema (especially `rank` as int, not string).

### Issue 3: C# Deserialization Errors

**Symptom**: `JsonException: The input does not contain any JSON elements`

**Cause**: Empty or malformed JSON payload from Redis

**Mitigation**: Check Redis payload:
```bash
redis-cli XRANGE movies_stream - + | head -1
```

**Resolution**: Verify scraper is publishing valid JSON before fixes.

## Testing Checklist

Before signing off on deployment:

- [ ] All contract tests pass (`pytest contracts/test_contracts.py -v`)
- [ ] Scraper publishes valid MoviePayload to Redis
- [ ] .NET Worker deserializes and validates payloads
- [ ] Database UPSERT works correctly
- [ ] API reads movies and returns DatabaseMovie schema
- [ ] AI Worker receives AITaskPayload and processes it
- [ ] Swagger UI shows updated schemas
- [ ] No schema violations in logs
- [ ] End-to-end flow works (scrape → Redis → DB → API → AI)
- [ ] Health checks pass for all services

## Monitoring After Deployment

### Key Metrics to Watch

1. **Redis Streams**
   - `XLEN movies_stream` - Should be growing as scraper runs
   - `XLEN ai_stream` - Should be growing as tasks are enqueued
   - Consumer group lag - Should be minimal

2. **Database**
   ```sql
   -- Check movie counts by status
   SELECT status, COUNT(*) FROM movies GROUP BY status;
   
   -- Check recent updates
   SELECT title, status, updated_at FROM movies 
   WHERE updated_at > NOW() - INTERVAL '1 hour' 
   ORDER BY updated_at DESC LIMIT 10;
   
   -- Check for NULL values in critical fields
   SELECT COUNT(*) FROM movies WHERE imdb_id IS NULL OR rank IS NULL;
   ```

3. **Application Logs**
   - Look for `contract_violation` or `ValidationError`
   - Check for schema mismatch warnings
   - Monitor error rates in each service

4. **API Endpoints**
   ```bash
   # Periodic checks
   curl http://localhost:8000/health
   curl http://localhost:8000/ready
   curl http://localhost:8000/movies?limit=1 | jq '.'
   ```

## Rollback Criteria

Rollback immediately if:
- [ ] Any service fails to start
- [ ] Contract validation errors in production logs
- [ ] Data integrity issues (NULL values in required fields)
- [ ] Redis stream corruption
- [ ] Database migration failed
- [ ] More than 5% of messages rejected due to schema violation

## Post-Deployment Tasks

After 24 hours of successful operation:

1. **Remove Old Contracts** (if keeping backup)
   - Delete duplicate contract definitions from individual services
   - Update documentation links

2. **Update CI/CD**
   - Add contract tests to pipeline
   - Add schema validation checks

3. **Team Training**
   - Review contract documentation with team
   - Document new contract usage patterns
   - Update runbooks

4. **Archive**
   - Document deployment process in wiki
   - Keep this guide for future reference
   - Update CHANGELOG.md

## Support & Escalation

**Issues During Deployment?**

1. Check logs: `docker compose logs <service_name>`
2. Review [contracts/README.md](../contracts/README.md) for contract details
3. Review [contracts/INTEGRATION_GUIDE.md](../contracts/INTEGRATION_GUIDE.md) for usage examples
4. Run diagnostic: `python test_contracts_manual.py`

**Need Rollback?**

See "Rollback Plan" section above.

---

**Deployment Owner**: _________  
**Deployment Date**: _________  
**Deployment Status**: ⚪ Pending | 🟡 In Progress | 🟢 Complete | 🔴 Rolled Back
