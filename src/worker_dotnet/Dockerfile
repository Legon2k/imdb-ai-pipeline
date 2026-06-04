# Stage 1: Build environment (SDK)
FROM mcr.microsoft.com/dotnet/sdk:10.0-preview AS build
WORKDIR /app

# Copy the solution and project files first to cache layers (optimizes build time)
COPY ["ImdbWorker.slnx", "./"]
COPY ["src/ImdbWorker.Service/ImdbWorker.Service.csproj", "src/ImdbWorker.Service/"]
RUN dotnet restore

# Copy the remaining source code
COPY . .

# Copy the single-source-of-truth VERSION file from the monorepo root
COPY VERSION ./

# Publish the application, baking the version string from VERSION file at compile-time
WORKDIR /app/src/ImdbWorker.Service
RUN dotnet publish -c Release -o /app/publish \
    /p:UseAppHost=false \
    /p:Version=$(cat /app/VERSION) \
    /p:InformationalVersion=$(cat /app/VERSION)

# Stage 2: Runtime environment (minimal footprint)
FROM mcr.microsoft.com/dotnet/aspnet:10.0-preview AS runtime
WORKDIR /app

# Install necessary dependencies for Kerberos/GSSAPI
RUN apt-get update && apt-get install -y \
    libkrb5-dev \
    && rm -rf /var/lib/apt/lists/*
    
COPY --from=build /app/publish .

# Define the entrypoint for the worker service
ENTRYPOINT ["dotnet", "ImdbWorker.Service.dll"]