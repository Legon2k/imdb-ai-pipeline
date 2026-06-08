package config

import (
	"fmt"
	"log/slog"
	"os"
	"strings"

	"github.com/caarlos0/env/v11"
)

type Config struct {
	// Database
	PgHost string `env:"POSTGRES_HOST" envDefault:"localhost"`
	PgPort string `env:"POSTGRES_PORT" envDefault:"5432"`
	PgUser string `env:"POSTGRES_USER" envDefault:"imdb_admin"`
	PgPass string `env:"POSTGRES_PASSWORD" envDefault:"supersecretpassword"`
	PgDb   string `env:"POSTGRES_DB" envDefault:"imdb_ai_db"`

	// Redis
	RedisHost string `env:"REDIS_HOST" envDefault:"localhost"`
	RedisPort string `env:"REDIS_PORT" envDefault:"6379"`

	// Logging
	LogLevel string `env:"LOG_LEVEL" envDefault:"INFO"`

	// Streams
	StreamName    string `env:"MOVIES_STREAM_NAME" envDefault:"movies_stream"`
	ConsumerGroup string `env:"MOVIES_CONSUMER_GROUP" envDefault:"imdb_worker"`
	ConsumerName  string `env:"MOVIES_CONSUMER_NAME"`
}

func Load() (*Config, error) {
	var cfg Config
	if err := env.Parse(&cfg); err != nil {
		return nil, fmt.Errorf("unable to parse configuration: %w", err)
	}

	if cfg.ConsumerName == "" {
		hostname, err := os.Hostname()
		if err != nil {
			cfg.ConsumerName = "go-worker-unknown"
		} else {
			cfg.ConsumerName = hostname
		}
	}

	return &cfg, nil
}

func (c *Config) GetPgConnectionString() string {
	return fmt.Sprintf("host=%s port=%s dbname=%s user=%s password=%s sslmode=disable",
		c.PgHost, c.PgPort, c.PgDb, c.PgUser, c.PgPass)
}

func (c *Config) GetRedisAddr() string {
	return fmt.Sprintf("%s:%s", c.RedisHost, c.RedisPort)
}

func (c *Config) GetLogLevel() slog.Level {
	switch strings.ToUpper(c.LogLevel) {
	case "DEBUG":
		return slog.LevelDebug
	case "WARNING":
		return slog.LevelWarn
	case "ERROR":
		return slog.LevelError
	default:
		return slog.LevelInfo
	}
}
