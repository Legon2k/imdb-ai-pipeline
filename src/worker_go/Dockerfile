# --- Stage 1: Build the static Go binary ---
FROM golang:1.24-alpine AS builder

# Install system dependencies required for compilation and module fetching
RUN apk add --no-cache ca-certificates tzdata git

WORKDIR /app

# Copy dependency manifests relative to the monorepo build context.
# Leveraging layer caching: this step only runs when go.mod or go.sum changes.
COPY src/worker_go/go.mod src/worker_go/go.sum ./
RUN go mod download

# Copy the actual worker source code
COPY src/worker_go/ .

# Copy the single-source-of-truth VERSION file from the monorepo root context
COPY VERSION ./

# Compile static binary and inject the version string from VERSION file at compile-time via ldflags
RUN CGO_ENABLED=0 GOOS=linux go build \
    -ldflags="-w -s -X main.Version=$(cat VERSION)" \
    -o /app/imdb_worker_go \
    ./cmd/worker

# --- Stage 2: Final alpine runtime image ---
FROM alpine:3.19

RUN apk add --no-cache ca-certificates tzdata

WORKDIR /app

# Copy the self-contained static binary from the builder stage
COPY --from=builder /app/imdb_worker_go .

# Enforce non-root execution for standard container security compliance
USER 10001:10001

CMD ["./imdb_worker_go"]