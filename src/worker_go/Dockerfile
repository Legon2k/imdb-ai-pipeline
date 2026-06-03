# --- Stage 1: Build the static Go binary ---
FROM golang:1.24-alpine AS builder

# Install certificates, timezone data and git (git is required by go mod tidy to fetch packages)
RUN apk add --no-cache ca-certificates tzdata git

WORKDIR /app

# Copy ONLY go.mod. We will generate a clean go.sum inside the container.
COPY go.mod ./
RUN go mod tidy

# Copy the rest of the source code
COPY . .

# Compile static binary.
RUN CGO_ENABLED=0 GOOS=linux go build \
    -ldflags="-w -s" \
    -o /app/imdb_worker_go \
    ./cmd/worker

# --- Stage 2: Final minimal runtime image ---
FROM alpine:3.19

RUN apk add --no-cache ca-certificates tzdata

WORKDIR /app

# Copy binary from the builder stage
COPY --from=builder /app/imdb_worker_go .

# Ensure VERSION file fallback exists in runtime
RUN echo "1.0.0-go" > /app/VERSION

# Run as non-root user
USER 10001:10001

CMD ["./imdb_worker_go"]