// --- START OF FILE Program.cs ---

using StackExchange.Redis;
using ImdbWorker.Service;

var builder = Host.CreateApplicationBuilder(args);

// 1. Redis Configuration
var redisHost = builder.Configuration["REDIS_HOST"] ?? "localhost";
var redisPort = builder.Configuration["REDIS_PORT"] ?? "6379";
builder.Services.AddSingleton<IConnectionMultiplexer>(sp => 
    ConnectionMultiplexer.Connect($"{redisHost}:{redisPort},abortConnect=false"));

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