// --- START OF FILE Worker.cs ---
// Shared data contracts are defined in ImdbWorker.Contracts namespace
// See contracts/CsharpContracts.cs for single source of truth

using System.Text.Json;
using System.Text.Json.Serialization;
using Dapper;
using Npgsql;
using StackExchange.Redis;
using ImdbWorker.Contracts;

namespace ImdbWorker.Service;

public class Worker : BackgroundService
{
    private readonly ILogger<Worker> _logger;
    private readonly IConnectionMultiplexer _redis;
    private readonly string _pgConnectionString;
    private readonly string _streamName;
    private readonly string _consumerGroup;
    private readonly string _consumerName;
    private const string PayloadField = "payload";

    public Worker(ILogger<Worker> logger, IConnectionMultiplexer redis, PostgresConfig pgConfig)
    {
        _logger = logger;
        _redis = redis;
        _pgConnectionString = pgConfig.ConnectionString;
        _streamName = Environment.GetEnvironmentVariable("MOVIES_STREAM_NAME") ?? "movies_stream";
        _consumerGroup = Environment.GetEnvironmentVariable("MOVIES_CONSUMER_GROUP") ?? "imdb_worker";
        _consumerName = Environment.GetEnvironmentVariable("MOVIES_CONSUMER_NAME") ?? Environment.MachineName;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation(
            "IMDB Worker started. Listening to stream {StreamName} as {ConsumerGroup}/{ConsumerName}",
            _streamName,
            _consumerGroup,
            _consumerName
        );
        var db = _redis.GetDatabase();
        await EnsureConsumerGroupAsync(db);

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                var entries = await db.StreamReadGroupAsync(
                    _streamName,
                    _consumerGroup,
                    _consumerName,
                    ">",
                    count: 1
                );

                if (entries.Length == 0)
                {
                    entries = await db.StreamReadGroupAsync(
                        _streamName,
                        _consumerGroup,
                        _consumerName,
                        "0",
                        count: 1
                    );
                }

                if (entries.Length > 0)
                {
                    await ProcessEntryAsync(db, entries[0], stoppingToken);
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

    private async Task EnsureConsumerGroupAsync(IDatabase db)
    {
        try
        {
            await db.StreamCreateConsumerGroupAsync(
                _streamName,
                _consumerGroup,
                "0-0",
                createStream: true
            );
        }
        catch (RedisServerException ex) when (ex.Message.Contains("BUSYGROUP"))
        {
            // Group already exists; this is expected on restarts.
        }
    }

    private async Task ProcessEntryAsync(IDatabase db, StreamEntry entry, CancellationToken ct)
    {
        var payload = entry.Values.FirstOrDefault(value => value.Name == PayloadField).Value;
        if (!payload.HasValue)
        {
            _logger.LogWarning("Skipping stream entry {MessageId}: missing payload field", entry.Id);
            await db.StreamAcknowledgeAsync(_streamName, _consumerGroup, entry.Id);
            return;
        }

        MoviePayload? movie;
        try
        {
            movie = JsonSerializer.Deserialize<MoviePayload>(payload.ToString());
        }
        catch (JsonException ex)
        {
            _logger.LogWarning(ex, "Skipping stream entry {MessageId}: invalid movie payload", entry.Id);
            await db.StreamAcknowledgeAsync(_streamName, _consumerGroup, entry.Id);
            return;
        }

        if (movie == null)
        {
            _logger.LogWarning("Skipping stream entry {MessageId}: empty movie payload", entry.Id);
            await db.StreamAcknowledgeAsync(_streamName, _consumerGroup, entry.Id);
            return;
        }

        // Validate the movie against contract constraints
        try
        {
            movie.Validate();
        }
        catch (ArgumentException ex)
        {
            _logger.LogWarning(ex, "Skipping stream entry {MessageId}: contract validation failed", entry.Id);
            await db.StreamAcknowledgeAsync(_streamName, _consumerGroup, entry.Id);
            return;
        }

        await SaveMovieToDatabaseAsync(movie, ct);
        await db.StreamAcknowledgeAsync(_streamName, _consumerGroup, entry.Id);
        _logger.LogInformation("Saved to DB and acknowledged stream entry: {Title}", movie.Title);
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
