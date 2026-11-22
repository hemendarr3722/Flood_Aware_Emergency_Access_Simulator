# Phase 2 — Local database setup (Windows PowerShell version)
# Run from project root. Requires Docker Desktop running.
#
# Step 1: Start the container
# Step 2: Apply migrations
# Step 3: Verify schema
# Step 4: Run loaders
# Step 5: Run integration tests

$ContainerName = "flood_aware_postgis"
$PgUser = "flood_user"
$PgPassword = "flood_local_dev_only"
$PgDb = "flood_aware"
$PgPort = "15432"

$env:DATABASE_URL = "postgresql://${PgUser}:${PgPassword}@localhost:${PgPort}/${PgDb}"

function Start-DbContainer {
    $exists = docker inspect $ContainerName 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Container $ContainerName exists, starting..."
        docker start $ContainerName 2>$null
    } else {
        Write-Host "Creating PostGIS container: $ContainerName"
        docker run -d `
            --name $ContainerName `
            -e POSTGRES_USER=$PgUser `
            -e POSTGRES_PASSWORD=$PgPassword `
            -e POSTGRES_DB=$PgDb `
            -p "${PgPort}:5432" `
            postgis/postgis:17-3.5
    }

    Write-Host "Waiting for PostgreSQL to be ready..."
    for ($i = 1; $i -le 60; $i++) {
        $result = docker exec $ContainerName pg_isready -U $PgUser -d $PgDb -q 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "PostgreSQL ready after ${i}s"
            break
        }
        Start-Sleep 1
    }
}

function Apply-Migrations {
    Write-Host "`nApplying migration 001..."
    Get-Content "database\migrations\001_initial.sql" |
        docker exec -i $ContainerName psql -U $PgUser -d $PgDb

    Write-Host "`nApplying migration 002..."
    Get-Content "database\migrations\002_rls_and_schema_improvements.sql" |
        docker exec -i $ContainerName psql -U $PgUser -d $PgDb
}

function Verify-Schema {
    Write-Host "`nRunning verify.sql..."
    Get-Content "database\verify.sql" |
        docker exec -i $ContainerName psql -U $PgUser -d $PgDb
}

Write-Host "DATABASE_URL=$($env:DATABASE_URL)"
Write-Host ""
Write-Host "Run the functions in order:"
Write-Host "  Start-DbContainer"
Write-Host "  Apply-Migrations"
Write-Host "  Verify-Schema"
Write-Host "  python pipelines/load/run_all_loaders.py --confirm-write"
Write-Host "  pytest database/tests/test_db_integration.py -v"
