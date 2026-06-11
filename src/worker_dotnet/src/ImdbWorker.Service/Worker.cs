// Shared data contracts are defined in ImdbWorker.Contracts namespace
// See contracts/CsharpContracts.cs for single source of truth

using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Reflection;
using Dapper;
using Npgsql;
using StackExchange.Redis;
using ImdbWorker.Contracts;
using Prometheus; // Added Prometheus .NET library

namespace ImdbWorker.Service;

public class Worker : BackgroundService
{
    private readonly ILogger<Worker> _logger;
    private readonly IConnectionMultiplexer _redis;
    private readonly string _pgConnectionString;
    private readonly string _streamName;
    private readonly string _consumerGroup;
    private readonly string _consumerName;
    private readonly bool _simulateDbSave;
    private const string PayloadField = "payload";
    private const int LogBatchSize = 1000;
    private long _msgCounter = 0;
    private long _batchStartTicks = Stopwatch.GetTimestamp();

    // Prometheus counter for tracking processed message counts
    private static readonly Counter MoviesProcessedTotal = Metrics.CreateCounter(
        "movies_processed_total",
        "Total movies processed by the .NET worker by outcome.",
        new CounterConfiguration
        {
            LabelNames = new[] { "status" }
        }
    );

    // Prometheus histogram for tracking latency percentiles (P50, P95, P99)
    private static readonly Histogram MessageProcessingDuration = Metrics.CreateHistogram(
        "message_processing_duration_seconds",
        "Latency of a single message processing run (from read to ACK) in seconds.",
        new HistogramConfiguration
        {
            // Latency buckets optimized for millisecond-range stream processing
            Buckets = new[] { 0.00002, 0.00005, 0.0001, 0.0002, 0.0004, 0.0008, 0.0015,  0.003,   0.006,  0.012,  0.025,  0.05,  0.1 }
        }
    );

    private MetricServer? _metricServer;

    public Worker(ILogger<Worker> logger, IConnectionMultiplexer redis, PostgresConfig pgConfig, SimulationConfig simConfig)
    {
        _logger = logger;
        _redis = redis;
        _pgConnectionString = pgConfig.ConnectionString;
        _simulateDbSave = simConfig.SimulateDbSave;
        _streamName = Environment.GetEnvironmentVariable("MOVIES_STREAM_NAME") ?? "movies_stream";
        _consumerGroup = Environment.GetEnvironmentVariable("MOVIES_CONSUMER_GROUP") ?? "imdb_worker";
        _consumerName = Environment.GetEnvironmentVariable("MOVIES_CONSUMER_NAME") ?? Environment.MachineName;
    }

    private string GetCurrentLogLevel()
    {
        if (_logger.IsEnabled(LogLevel.Trace)) return "Trace";
        if (_logger.IsEnabled(LogLevel.Debug)) return "Debug";
        if (_logger.IsEnabled(LogLevel.Information)) return "Information";
        if (_logger.IsEnabled(LogLevel.Warning)) return "Warning";
        if (_logger.IsEnabled(LogLevel.Error)) return "Error";
        if (_logger.IsEnabled(LogLevel.Critical)) return "Critical";
        return "None";
    }    

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        // Start standalone Prometheus metric server on port 8002
        _metricServer = new MetricServer(port: 8002);
        _metricServer.Start();
        _logger.LogInformation("Prometheus metrics server started on port 8002. System and runtime metrics enabled.");

        var version = Environment.GetEnvironmentVariable("APP_VERSION") ?? "0.0.0-dev";

        _logger.LogInformation(
            "IMDB Worker v{Version} started. Log level: {LogLevel}. Simulate DB save: {SimulateDbSave}. Listening to stream {StreamName} as {ConsumerGroup}/{ConsumerName}",
            version,
            GetCurrentLogLevel(),
            _simulateDbSave,
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
        // Start high-resolution timing for latency percentile calculation
        var entryStartTicks = Stopwatch.GetTimestamp();

        var payload = entry.Values.FirstOrDefault(value => value.Name == PayloadField).Value;
        if (!payload.HasValue)
        {
            _logger.LogWarning("Skipping stream entry {MessageId}: missing payload field", entry.Id);
            MoviesProcessedTotal.WithLabels("validation_error").Inc();
            await db.StreamAcknowledgeAsync(_streamName, _consumerGroup, entry.Id);
            return;
        }

        MoviePayload? movie;
        try
        {
            movie = JsonSerializer.Deserialize<MoviePayload>(payload.ToString());
        }
        catch (JsonException)
        {
            _logger.LogWarning("Skipping stream entry {MessageId}: invalid movie payload", entry.Id);
            MoviesProcessedTotal.WithLabels("validation_error").Inc();
            await db.StreamAcknowledgeAsync(_streamName, _consumerGroup, entry.Id);
            return;
        }

        if (movie == null)
        {
            _logger.LogWarning("Skipping stream entry {MessageId}: empty movie payload", entry.Id);
            MoviesProcessedTotal.WithLabels("validation_error").Inc();
            await db.StreamAcknowledgeAsync(_streamName, _consumerGroup, entry.Id);
            return;
        }

        // Validate the movie against contract constraints
        try
        {
            movie.Validate();
        }
        catch (ArgumentException)
        {
            _logger.LogWarning("Skipping stream entry {MessageId}: contract validation failed", entry.Id);
            MoviesProcessedTotal.WithLabels("validation_error").Inc();
            await db.StreamAcknowledgeAsync(_streamName, _consumerGroup, entry.Id);
            return;
        }

        // Execute save only if DB simulation/bypass is disabled
        if (!_simulateDbSave)
        {
            try
            {
                await SaveMovieToDatabaseAsync(movie, ct);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Failed to save movie to database: {MessageId}", entry.Id);
                MoviesProcessedTotal.WithLabels("db_error").Inc();
                return; // Revert/do not ACK on DB write failure to allow retry
            }
        }
        
        await db.StreamAcknowledgeAsync(_streamName, _consumerGroup, entry.Id);
        MoviesProcessedTotal.WithLabels("success").Inc();

        // Stop timing and observe value in the histogram
        var elapsedSeconds = (Stopwatch.GetTimestamp() - entryStartTicks) / (double)Stopwatch.Frequency;
        MessageProcessingDuration.Observe(elapsedSeconds);

        if (_logger.IsEnabled(LogLevel.Debug))
        {
            _logger.LogDebug("Saved to DB and acknowledged stream entry: {Title}", movie.Title);
        }

        _msgCounter++;
        
        if (_msgCounter % LogBatchSize == 0)
        {
            var batchEndTicks = Stopwatch.GetTimestamp();
            var batchSeconds = (batchEndTicks - _batchStartTicks) / (double)Stopwatch.Frequency;
            var batchRps = batchSeconds > 0
                ? LogBatchSize / batchSeconds
                : 0;

            _logger.LogInformation(
                "[BATCH] Processed: {Processed} | Batch Time: {BatchTime:F3}s | Batch RPS: {BatchRps:F2}",
                _msgCounter,
                batchSeconds,
                batchRps
            );

            _batchStartTicks = Stopwatch.GetTimestamp();
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

    public override async Task StopAsync(CancellationToken cancellationToken)
    {
        _metricServer?.Stop();
        await base.StopAsync(cancellationToken);
    }
}