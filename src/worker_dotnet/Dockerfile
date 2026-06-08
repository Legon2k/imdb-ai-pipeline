# Stage 1: Build environment (SDK)
FROM mcr.microsoft.com/dotnet/sdk:10.0-preview AS build
WORKDIR /app

# Copy the project files from local context
COPY ["ImdbWorker.slnx", "./"]
COPY ["src/ImdbWorker.Service/ImdbWorker.Service.csproj", "src/ImdbWorker.Service/"]
RUN dotnet restore

# Copy the remaining dotnet source code
COPY . .

# Publish without compile-time variable injection
WORKDIR /app/src/ImdbWorker.Service
RUN dotnet publish -c Release -o /app/publish /p:UseAppHost=false

# Stage 2: Runtime environment
FROM mcr.microsoft.com/dotnet/aspnet:10.0-preview AS runtime
WORKDIR /app

RUN apt-get update && apt-get install -y \
    libkrb5-dev \
    && rm -rf /var/lib/apt/lists/*
    
COPY --from=build /app/publish .

ENTRYPOINT ["dotnet", "ImdbWorker.Service.dll"]