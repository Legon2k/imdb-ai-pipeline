// --- START OF FILE Worker.cs ---

using StackExchange.Redis;

namespace ImdbWorker.Service;

public class Worker : BackgroundService
{
    private readonly ILogger<Worker> _logger;
    private readonly IConnectionMultiplexer _redis;
    private const string QueueName = "movies_queue";

    // Inject Dependencies via constructor
    public Worker(ILogger<Worker> logger, IConnectionMultiplexer redis)
    {
        _logger = logger;
        _redis = redis;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("IMDB Worker started. Listening to Redis queue: {QueueName}", QueueName);
        
        var db = _redis.GetDatabase();

        // Run continuously until cancellation is requested (e.g., Docker stop)
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                // Pop from the right (RPOP) to process oldest messages first (FIFO)
                // We use ListRightPopAsync instead of blocking BLPOP to avoid thread starvation in .NET
                var redisValue = await db.ListRightPopAsync(QueueName);

                if (redisValue.HasValue)
                {
                    _logger.LogInformation("Success! Popped movie from queue.");
                    
                    // For Iteration 1, we just print the JSON payload to the console
                    // In Iteration 2, we will deserialize this and save it to PostgreSQL
                    _logger.LogInformation("Payload: {Payload}", redisValue.ToString());
                }
                else
                {
                    // Queue is empty, wait 1 second before polling again to save CPU cycles
                    await Task.Delay(1000, stoppingToken);
                }
            }
            catch (TaskCanceledException)
            {
                // Graceful shutdown requested, exit the loop cleanly
                break;
            }
            catch (Exception ex)
            {
                // Prevent the entire background service from crashing on transient errors
                _logger.LogError(ex, "Error occurred while polling Redis. Retrying in 5 seconds...");
                await Task.Delay(5000, stoppingToken);
            }
        }
        
        _logger.LogInformation("IMDB Worker gracefully stopped.");
    }
}