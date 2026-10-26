#!/bin/bash
set -e

# This script runs after PostgreSQL initialization
# It modifies pg_hba.conf to allow Docker network connections

PG_HBA="/var/lib/postgresql/data/pg_hba.conf"

# Wait for PostgreSQL to start
until pg_isready -U finagent -d finagent; do
  sleep 1
done

# Modify pg_hba.conf to allow connections from Docker network
if ! grep -q "0.0.0.0/0" "$PG_HBA"; then
  echo "Configuring pg_hba.conf for Docker network access..."
  # Remove any existing restrictive rules
  sed -i '/host all all all scram-sha-256/d' "$PG_HBA"
  # Add trust for all networks (for local development)
  echo "host    all             all             0.0.0.0/0               trust" >> "$PG_HBA"
  # Reload configuration
  psql -U finagent -d finagent -c "SELECT pg_reload_conf();"
fi
