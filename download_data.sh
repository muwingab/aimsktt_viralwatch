#!/bin/bash
set -e

REPO_URL="https://github.com/INRB-UMIE/BDBV2026-Data.git"
REPO_DIR="BDBV2026-Data"

echo "=== 1. Scaffolding Test Directory ==="
mkdir -p data_test

echo "=== 2. Setting up Git LFS (Large File Storage) ==="
# Ensure Git LFS is installed and active in your Codespace environment
git lfs install

echo "=== 3. Cloning/Updating INRB-UMIE Repository ==="
if [ ! -d "$REPO_DIR" ]; then
    echo "Cloning the repository..."
    git clone --depth 1 "$REPO_URL"
else
    echo "Repository already exists. Pulling latest..."
    git -C "$REPO_DIR" pull
fi

# Explicitly pull any LFS-tracked data blobs
echo "🚚 Pulling LFS data blobs..."
cd "$REPO_DIR" && git lfs pull && cd ..

echo "=== 4. Recursively Syncing CSVs into data_test/ ==="
# Find all CSV files inside any nested subdirectories and copy them directly to data_test/
find "$REPO_DIR" -name "*.csv" -exec cp {} data_test/ \;

echo "=== 5. Fetching WHO Bulletins into data_test/ ==="
curl -L -s -o data_test/DON602.html "https://www.who.int/emergencies/disease-outbreak-news/item/DON602"
curl -L -s -o data_test/DON603.html "https://www.who.int/emergencies/disease-outbreak-news/item/DON603"

echo "=== 6. Verifying Integrity ==="
# Count how many CSV files we successfully copied into our test folder
CSV_COUNT=$(ls data_test/*.csv 2>/dev/null | wc -l)

if [ "$CSV_COUNT" -gt 0 ]; then
    echo "✔ Ingestion verification successful! Found and copied $CSV_COUNT CSV data tables to data_test/"
    echo "📂 Files present in data_test/:"
    ls data_test/
else
    echo "❌ INGESTION ERROR: No CSV files were retrieved from the repository." >&2
    exit 1
fi
