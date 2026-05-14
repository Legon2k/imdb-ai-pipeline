// --- START OF FILE Worker.cs ---

using System.Text.Json;
using System.Text.Json.Serialization;
using Dapper;
using Npgsql;
using StackExchange.Redis;

namespace ImdbWorker.Service;

// 1. Data Contract (Matches the Python JSON payload exactly)
public record MoviePayload(
    [property: JsonPropertyName("imdb_id")] string ImdbId,
    [property: JsonPropertyName("rank")] int Rank,
    [property: JsonPropertyName("title")] string Title,
    [property: JsonPropertyName("rating")] decimal Rating,
    [property: JsonPropertyName("votes")] string Votes,
    [property: JsonPropertyName("image_url")] string? ImageUrl
);

public class Worker : BackgroundService
{
    private readonly ILogger<Worker> _logger;
    private readonly IConnectionMultiplexer _redis;
    private readonly string _pgConnectionString;
    private const string QueueName = "movies_queue";

    public Worker(ILogger<Worker> logger, IConnectionMultiplexer redis, PostgresConfig pgConfig)
    {
        _logger = logger;
        _redis = redis;
        _pgConnectionString = pgConfig.ConnectionString;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("IMDB Worker started. Listening to {QueueName}", QueueName);
        var db = _redis.GetDatabase();

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                var redisValue = await db.ListRightPopAsync(QueueName);

                if (redisValue.HasValue)
                {
                    // 2. Deserialize JSON
                    var movie = JsonSerializer.Deserialize<MoviePayload>(redisValue.ToString()!);
                    
                    if (movie != null)
                    {
                        // 3. Save to PostgreSQL using Dapper
                        await SaveMovieToDatabaseAsync(movie, stoppingToken);
                        _logger.LogInformation("Saved to DB: {Title}", movie.Title);
                    }
                }
                else
                {
                    await Task.Delay(1000, stoppingToken);
                }
            }
            catch (Exception ex) when (ex is not TaskCanceledException)
            {
                _logger.LogError(ex, "Error processing message. Retrying...");
                await Task.Delay(5000, stoppingToken);
            }
        }
    }

    private async Task SaveMovieToDatabaseAsync(MoviePayload movie, CancellationToken ct)
    {
        // SQL UPSERT: Insert if not exists, otherwise update rating and rank
        const string sql = @"
            INSERT INTO movies (imdb_id, rank, title, rating, votes, image_url, status)
            VALUES (@ImdbId, @Rank, @Title, @Rating, @Votes, @ImageUrl, 'pending')
            ON CONFLICT (imdb_id) DO UPDATE 
            SET rank = EXCLUDED.rank,
                rating = EXCLUDED.rating,
                votes = EXCLUDED.votes,
                updated_at = CURRENT_TIMESTAMP;";

        await using var connection = new NpgsqlConnection(_pgConnectionString);
        await connection.ExecuteAsync(new CommandDefinition(sql, movie, cancellationToken: ct));
    }
}