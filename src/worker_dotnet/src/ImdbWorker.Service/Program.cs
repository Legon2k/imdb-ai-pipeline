using StackExchange.Redis;
using ImdbWorker.Service;

var processStartTime = System.Diagnostics.Process.GetCurrentProcess().StartTime.ToUniversalTime();

var builder = Host.CreateApplicationBuilder(args);

if (string.Equals(builder.Configuration["Logging:LogLevel:Default"], "INFO", StringComparison.OrdinalIgnoreCase))
{
    builder.Configuration["Logging:LogLevel:Default"] = "Information";
}

// Helper function to parse simulate DB save flag
bool ParseSimulateDbSave(string? value)
{
    if (string.IsNullOrEmpty(value)) return false;
    var normalized = value.ToLowerInvariant().Trim();
    return normalized == "true" || normalized == "yes" || normalized == "1" || normalized == "on";
}

// 1. Redis Configuration
var redisHost = builder.Configuration["REDIS_HOST"] ?? "localhost";
var redisPort = builder.Configuration["REDIS_PORT"] ?? "6379";
var simulateDbSave = ParseSimulateDbSave(builder.Configuration["SIMULATE_SAVE_MOVIE_TO_DATABASE"]);

builder.Services.AddSingleton<IConnectionMultiplexer>(sp =>
{
    var redis = ConnectionMultiplexer.Connect($"{redisHost}:{redisPort},abortConnect=false");
    var redisReadyTicks = System.Diagnostics.Stopwatch.GetTimestamp();
    var coldStartMs = (DateTime.UtcNow - processStartTime).TotalMilliseconds;
    sp.GetRequiredService<ILoggerFactory>()
        .CreateLogger("Startup")
        .LogInformation(
            "Cold start completed in {ColdStartMs:F2} ms. Redis ready ticks: {RedisReadyTicks}",
            coldStartMs,
            redisReadyTicks
        );

    return redis;
});

builder.Services.AddSingleton(new SimulationConfig(simulateDbSave));

// 2. PostgreSQL Configuration
var pgUser = builder.Configuration["POSTGRES_USER"] ?? "imdb_admin";
var pgPass = builder.Configuration["POSTGRES_PASSWORD"] ?? "supersecretpassword";
var pgDb = builder.Configuration["POSTGRES_DB"] ?? "imdb_ai_db";
var pgHost = builder.Configuration["POSTGRES_HOST"] ?? "localhost"; // Local fallback
// When running in Docker, POSTGRES_HOST should be "imdb_postgres"

var connectionString = $"Host={pgHost};Database={pgDb};Username={pgUser};Password={pgPass}";
builder.Services.AddSingleton(new PostgresConfig(connectionString));

// 3. Register Worker
builder.Services.AddHostedService<Worker>();

var host = builder.Build();
host.Run();

// Simple record to inject connection string
public record PostgresConfig(string ConnectionString);

public record SimulationConfig(bool SimulateDbSave);
