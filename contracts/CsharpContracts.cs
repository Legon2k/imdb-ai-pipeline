// GENERATED FROM contracts/schemas.json - DO NOT EDIT MANUALLY
// Update contracts/schemas.json and regenerate this file

using System.Text.Json.Serialization;

namespace ImdbWorker.Contracts;

/// <summary>
/// Core movie data structure flowing through: Scraper → Redis → Database.
/// Single source of truth for movie payload validation.
/// 
/// Fields must exactly match contracts/schemas.json#/definitions/MoviePayload
/// </summary>
public record MoviePayload(
    [property: JsonPropertyName("imdb_id")]
    string ImdbId,

    [property: JsonPropertyName("rank")]
    int Rank,

    [property: JsonPropertyName("title")]
    string Title,

    [property: JsonPropertyName("rating")]
    decimal Rating,

    [property: JsonPropertyName("votes")]
    string Votes,

    [property: JsonPropertyName("image_url")]
    string? ImageUrl = null
)
{
    /// <summary>
    /// Validates the contract against known constraints.
    /// Should be called after deserialization from Redis.
    /// </summary>
    public void Validate()
    {
        if (string.IsNullOrWhiteSpace(ImdbId) || !System.Text.RegularExpressions.Regex.IsMatch(ImdbId, @"^tt\d+$"))
            throw new ArgumentException($"Invalid imdb_id format: {ImdbId}", nameof(ImdbId));

        if (Rank < 1 || Rank > 250)
            throw new ArgumentException($"Rank must be between 1 and 250, got {Rank}", nameof(Rank));

        if (Title.Length == 0 || Title.Length > 255)
            throw new ArgumentException($"Title length must be 1-255, got {Title.Length}", nameof(Title));

        if (Rating < 0 || Rating > 10)
            throw new ArgumentException($"Rating must be between 0 and 10, got {Rating}", nameof(Rating));

        if (string.IsNullOrWhiteSpace(Votes))
            throw new ArgumentException("Votes cannot be empty", nameof(Votes));
    }
}

/// <summary>
/// Subset of movie data for AI enrichment tasks.
/// Contract flowing: API → Redis ai_stream → AI Worker
/// 
/// Fields must exactly match contracts/schemas.json#/definitions/AITaskPayload
/// </summary>
public record AITaskPayload(
    [property: JsonPropertyName("id")]
    int Id,

    [property: JsonPropertyName("rank")]
    int Rank,

    [property: JsonPropertyName("title")]
    string Title,

    [property: JsonPropertyName("rating")]
    decimal Rating
)
{
    /// <summary>
    /// Validates the contract against known constraints.
    /// </summary>
    public void Validate()
    {
        if (Id < 1)
            throw new ArgumentException($"Id must be positive, got {Id}", nameof(Id));

        if (Rank < 1 || Rank > 250)
            throw new ArgumentException($"Rank must be between 1 and 250, got {Rank}", nameof(Rank));

        if (Title.Length == 0 || Title.Length > 255)
            throw new ArgumentException($"Title length must be 1-255, got {Title.Length}", nameof(Title));

        if (Rating < 0 || Rating > 10)
            throw new ArgumentException($"Rating must be between 0 and 10, got {Rating}", nameof(Rating));
    }
}

/// <summary>
/// Complete movie record as persisted in PostgreSQL.
/// Used for database responses and contract testing.
/// </summary>
public record DatabaseMovie(
    [property: JsonPropertyName("id")]
    int Id,

    [property: JsonPropertyName("imdb_id")]
    string ImdbId,

    [property: JsonPropertyName("rank")]
    int Rank,

    [property: JsonPropertyName("title")]
    string Title,

    [property: JsonPropertyName("rating")]
    decimal Rating,

    [property: JsonPropertyName("votes")]
    string Votes,

    [property: JsonPropertyName("image_url")]
    string? ImageUrl,

    [property: JsonPropertyName("ai_summary")]
    string? AiSummary,

    [property: JsonPropertyName("status")]
    string Status,

    [property: JsonPropertyName("created_at")]
    DateTime CreatedAt,

    [property: JsonPropertyName("updated_at")]
    DateTime UpdatedAt
);
