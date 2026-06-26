# --- Stage 1: Build the static Go binary ---
FROM golang:1.24-alpine AS builder

# Install build dependencies
RUN apk add --no-cache ca-certificates tzdata git

WORKDIR /app

# Copy manifests first to utilize Docker layer caching
COPY go.mod go.sum ./
RUN go mod download

# Copy the rest of the source code
COPY . .

# Compile static binary with optimizations and stripped debug symbols
RUN CGO_ENABLED=0 GOOS=linux go build \
    -ldflags="-w -s" \
    -o /app/imdb_worker_go \
    ./cmd/worker

# --- Stage 2: Final secure runtime image ---
# Use active supported Alpine version (as of mid-2026)
FROM alpine:3.24

RUN apk add --no-cache ca-certificates tzdata

# Create a non-privileged system group and user
RUN addgroup -g 10001 -S appgroup && \
    adduser -u 10001 -S appuser -G appgroup

WORKDIR /app

# Copy the compiled binary and grant permissions to the non-root user
COPY --from=builder /app/imdb_worker_go .
RUN chown -R appuser:appgroup /app

# Switch to the non-privileged user
USER appuser

CMD ["./imdb_worker_go"]