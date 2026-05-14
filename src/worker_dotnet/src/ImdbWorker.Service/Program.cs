// --- START OF FILE Program.cs ---

using StackExchange.Redis;
using ImdbWorker.Service;

var builder = Host.CreateApplicationBuilder(args);

// Fetch Redis configuration from Environment Variables (injected by Docker via .env)
var redisHost = builder.Configuration["REDIS_HOST"] ?? "localhost";
var redisPort = builder.Configuration["REDIS_PORT"] ?? "6379";

// abortConnect=false ensures the application doesn't crash if Redis is temporarily unavailable
var connectionString = $"{redisHost}:{redisPort},abortConnect=false";

// Register Redis ConnectionMultiplexer as a Singleton (Best Practice for SE.Redis)
builder.Services.AddSingleton<IConnectionMultiplexer>(sp => 
    ConnectionMultiplexer.Connect(connectionString));

// Register our background worker
builder.Services.AddHostedService<Worker>();

var host = builder.Build();
host.Run();