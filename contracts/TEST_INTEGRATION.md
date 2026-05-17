# Contract Tests in CI/CD Pipeline

## Overview

Contract synchronization tests are now integrated into:
- ✅ **CI Pipeline** (`.github/workflows/ci.yml`)
- ✅ **Docker Compose** (with `test` profile)
- ✅ **Makefile** (convenient commands)

## Running Contract Tests

### Locally (on developer machine)

**Basic run:**
```bash
make test-contracts
```

**With dependencies installed:**
```bash
make install-test
python -m pytest contracts/test_contracts.py -v --tb=short
```

**With verbose output:**
```bash
python -m pytest contracts/test_contracts.py -vv --tb=long
```

**With coverage report:**
```bash
python -m pytest contracts/test_contracts.py --cov=contracts --cov-report=html
```

### In Docker Container

**Run tests in container:**
```bash
docker compose --profile test up contract-tests
```

**With logs output:**
```bash
docker compose --profile test up contract-tests --no-build
docker compose --profile test logs -f contract-tests
```

### In CI Pipeline

Contract tests run automatically in GitHub Actions on:
- ✅ `git push` to `main` branch
- ✅ Pull requests to `main`
- ✅ Manual trigger via `workflow_dispatch`

**View results:**
1. Go to https://github.com/your-repo/actions
2. Select latest workflow run
3. Find job **"Python Lint & Tests"** → **"Contract sync tests"**

## What Gets Tested

### Contract Validation

✅ **Schema Sync** - Pydantic models match JSON Schema  
✅ **MoviePayload** - All validation rules (bounds, formats)  
✅ **AITaskPayload** - Required fields and type checking  
✅ **DatabaseMovie** - Status enum and optional fields  
✅ **Cross-Contract** - Contract hierarchy (subset/superset)

### Example Checks

```python
# ✓ Valid payloads
MoviePayload(imdb_id='tt0111161', rank=1, title='Test', rating=9.0, votes='1000')

# ✗ Invalid values rejected
MoviePayload(imdb_id='invalid', rank=1, ...)  # Wrong format
MoviePayload(imdb_id='tt0111161', rank=251, ...)  # rank > 250
MoviePayload(imdb_id='tt0111161', rank=1, rating=10.5, ...)  # rating > 10
```

## Test Results

### Successful Run

```
✓ Valid payload accepted
✓ Invalid rank rejected (rank > 250)
✓ Invalid imdb_id rejected (wrong format)
✓ Missing imdb_id rejected
✓ Invalid id rejected (id < 1)
✓ Valid database movie accepted
✓ Invalid status rejected

✓ All validation tests passed!
======================== 30 passed in 2.5s =========================
```

### Contract Error

If a test fails, it means:

**Example error:**
```
FAILED contracts/test_contracts.py::MoviePayloadValidationTest::test_invalid_rank_too_high
ValidationError: 1 validation error for MoviePayload
rank
  Input should be less than or equal to 250 [type=less_than_equal, input_value=251, input_type=int]
```

**Solution:**
1. Verify all services use shared contracts
2. Run: `make test-contracts -v`
3. Find which service violates the contract

## Git Workflow Integration

### Before Push

```bash
# Run all tests before commit
make test-all

# If all pass:
git add .
git commit -m "feature: update contracts"
git push
```

### CI Automation

GitHub Actions will:

1. ✅ Download code
2. ✅ Install Python 3.11
3. ✅ Run Ruff lint/format
4. ✅ Run scraper unit tests
5. ✅ Run API smoke tests
6. ✅ **Run contract sync tests** ← New!
7. ✅ Run .NET build
8. ✅ Run docker compose build

If any test fails - PR is blocked from merge.

## Troubleshooting

### "ModuleNotFoundError: No module named 'pytest'"

```bash
make install-test
# or
pip install -r requirements-test.txt
```

### "No such file or directory: 'contracts/test_contracts.py'"

Make sure you're in the project root directory:
```bash
cd /path/to/imdb-ai-pipeline
make test-contracts
```

### Docker container won't start

```bash
# Check that Dockerfile.test exists
ls -la Dockerfile.test

# Rebuild image
docker compose --profile test build --no-cache contract-tests

# Run with verbose output
docker compose --profile test up contract-tests --verbose
```

### CI tests fail but pass locally

This might be Python version. CI uses Python 3.11:
```bash
python3.11 -m pytest contracts/test_contracts.py
```

## Best Practices

### For Developers

1. **Before changing contracts:**
   ```bash
   make test-contracts  # Verify all tests pass
   ```

2. **After adding new field:**
   - Update `contracts/schemas.json`
   - Update `contracts/python_contracts.py` (Pydantic)
   - Update `ImdbWorker.Service/Contracts.cs` (C#)
   - Run: `make test-contracts`

3. **When adding new validation rule:**
   - Add test to `contracts/test_contracts.py`
   - Verify test fails first (TDD)
   - Реализовать validation
   - Убедитесь, что тест проходит

### Для code review

Проверяющий должен убедиться:
- ✅ Контрактные тесты прошли в CI
- ✅ Нет регрессий в других тестах
- ✅ Все 3 представления контракта обновлены (JSON, Python, C#)
- ✅ Новые тесты добавлены при необходимости

## Мониторинг в production

### Проверка синхронизации контрактов

```bash
# В контейнере production:
docker compose exec api python -m pytest /app/contracts/test_contracts.py -v
```

### Если контракты рассинхронизируются

1. Проверить логи каждого сервиса
2. Найти, какой сервис нарушает контракт
3. Откатить к последней известной хорошей версии
4. Развернуть исправленную версию

## Ссылки

- [contracts/README.md](../contracts/README.md) - Полная документация
- [contracts/INTEGRATION_GUIDE.md](../contracts/INTEGRATION_GUIDE.md) - Примеры использования
- [DEPLOYMENT_CONTRACTS.md](DEPLOYMENT_CONTRACTS.md) - Deployment Plan
- [.github/workflows/ci.yml](../.github/workflows/ci.yml) - CI конфигурация
- [docker-compose.yml](../docker-compose.yml) - Docker конфигурация
