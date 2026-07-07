-- Separate database for Evolution API.
-- The primary app database is created automatically via POSTGRES_DB.
SELECT 'CREATE DATABASE evolution'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'evolution')\gexec
