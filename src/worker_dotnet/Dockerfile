# --- START OF FILE Dockerfile ---

# Stage 1: Build environment (SDK)
FROM mcr.microsoft.com/dotnet/sdk:10.0-preview AS build
WORKDIR /app

# Copy the solution and project files first to cache layers (optimizes build time)
COPY ["ImdbWorker.slnx", "./"]
COPY ["src/ImdbWorker.Service/ImdbWorker.Service.csproj", "src/ImdbWorker.Service/"]
RUN dotnet restore

# Copy the remaining source code and build the application
COPY . .
WORKDIR /app/src/ImdbWorker.Service
RUN dotnet publish -c Release -o /app/publish /p:UseAppHost=false

# Stage 2: Runtime environment (minimal footprint)
FROM mcr.microsoft.com/dotnet/aspnet:10.0-preview AS runtime
WORKDIR /app
COPY --from=build /app/publish .

# Define the entrypoint for the worker service
ENTRYPOINT ["dotnet", "ImdbWorker.Service.dll"]