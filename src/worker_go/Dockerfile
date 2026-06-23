# --- Stage 1: Build the static Go binary ---
FROM golang:1.24-alpine AS builder

RUN apk add --no-cache ca-certificates tzdata git

WORKDIR /app

# Copy Go manifests from local context
COPY go.mod ./
RUN go mod download || true

# Copy all source code
COPY . .

# Update dependencies to ensure go.sum is complete
RUN go mod tidy

# Compile static binary without any complex build arguments
RUN CGO_ENABLED=0 GOOS=linux go build \
    -ldflags="-w -s" \
    -o /app/imdb_worker_go \
    ./cmd/worker

# --- Stage 2: Final alpine runtime image ---
FROM alpine:3.19

RUN apk add --no-cache ca-certificates tzdata

WORKDIR /app

COPY --from=builder /app/imdb_worker_go .

USER 10001:10001

CMD ["./imdb_worker_go"]