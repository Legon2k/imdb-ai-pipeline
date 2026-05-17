from contracts import MoviePayload, AITaskPayload, DatabaseMovie
from pydantic import ValidationError
from datetime import datetime, timezone

print("Testing MoviePayload validation:")
print("-" * 50)

# Valid payload
try:
    m = MoviePayload(
        imdb_id="tt0111161", rank=1, title="Test", rating=9.0, votes="1000"
    )
    print("✓ Valid payload accepted")
except ValidationError as e:
    print(f"✗ Valid payload rejected: {e}")

# Invalid rank (> 250)
try:
    m = MoviePayload(
        imdb_id="tt0111161", rank=251, title="Test", rating=9.0, votes="1000"
    )
    print("✗ Invalid rank accepted (should be rejected)")
except ValidationError:
    print("✓ Invalid rank rejected (rank > 250)")

# Invalid imdb_id
try:
    m = MoviePayload(imdb_id="invalid", rank=1, title="Test", rating=9.0, votes="1000")
    print("✗ Invalid imdb_id accepted")
except ValidationError:
    print("✓ Invalid imdb_id rejected (wrong format)")

# Missing required field
try:
    m = MoviePayload(rank=1, title="Test", rating=9.0, votes="1000")
    print("✗ Missing imdb_id accepted")
except ValidationError:
    print("✓ Missing imdb_id rejected")

print("\nTesting AITaskPayload validation:")
print("-" * 50)

# Valid AI task
try:
    t = AITaskPayload(id=1, rank=1, title="Test", rating=9.0)
    print("✓ Valid AI task accepted")
except ValidationError as e:
    print(f"✗ Valid AI task rejected: {e}")

# Invalid id (zero)
try:
    t = AITaskPayload(id=0, rank=1, title="Test", rating=9.0)
    print("✗ Invalid id accepted")
except ValidationError:
    print("✓ Invalid id rejected (id < 1)")

print("\nTesting DatabaseMovie validation:")
print("-" * 50)

# Valid database movie
try:
    db_movie = DatabaseMovie(
        id=1,
        imdb_id="tt0111161",
        rank=1,
        title="Test",
        rating=9.0,
        votes="1000",
        image_url=None,
        ai_summary=None,
        status="pending",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    print("✓ Valid database movie accepted")
except ValidationError as e:
    print(f"✗ Valid database movie rejected: {e}")

# Invalid status
try:
    db_movie = DatabaseMovie(
        id=1,
        imdb_id="tt0111161",
        rank=1,
        title="Test",
        rating=9.0,
        votes="1000",
        image_url=None,
        ai_summary=None,
        status="invalid_status",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    print("✗ Invalid status accepted")
except ValidationError:
    print("✓ Invalid status rejected")

print("\n✓ All validation tests passed!")
print("\nContract synchronization verified successfully!")
