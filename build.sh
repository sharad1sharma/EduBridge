#!/usr/bin/env bash
# Exit immediately if a command exits with a non-zero status
set -o errexit

echo "--- Installing Python Dependencies ---"
pip install --upgrade pip
pip install -r requirements.txt

echo "--- Collecting Static Files ---"
python manage.py collectstatic --no-input

echo "--- Applying Database Migrations ---"
python manage.py migrate

echo "--- Seeding Demo Data (if enabled) ---"
if [ "$SEED_DEMO_DATA" = "true" ] || [ "$SEED_DEMO_DATA" = "1" ]; then
    echo "SEED_DEMO_DATA is enabled. Seeding demo dataset..."
    python manage.py seed_demo_data
fi

echo "--- Build Completed Successfully ---"
