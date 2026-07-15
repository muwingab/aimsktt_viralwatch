import os
import glob
import pandas as pd
import numpy as np
from sqlalchemy import create_engine

# 1. Fetch Aiven Connection String from Environment
DATABASE_URL = os.environ.get("DATABASE_URL")

# Set up SQL connection (Fallback to SQLite inside data_test/ if no cloud URL is configured)
if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    engine = create_engine(DATABASE_URL)
    print("🔌 Connected successfully to your Cloud Aiven PostgreSQL database!")
else:
    engine = create_engine("sqlite:///data_test/viralwatch.db")
    print("📁 DATABASE_URL not found. Saving locally to data_test/viralwatch.db.")

# Translation Mapping for Bilingual Headers (French -> English)
COLUMN_TRANSLATIONS = {
    # Dates
    "date_notification": "date",
    "date_rapport": "date",
    "jour": "date",
    # Geography
    "zone_de_sante": "health_zone",
    "zone_sante": "health_zone",
    "nom_zone": "health_zone",
    "province": "province",
    # Metrics
    "cas_confirmes": "confirmed_cases",
    "cas_suspects": "suspected_cases",
    "deces": "deaths",
    "gueris": "recovered"
}

# Status/Value Translations (French -> English)
STATUS_TRANSLATIONS = {
    "oui": "yes",
    "non": "no",
    "vrai": "true",
    "faux": "false",
    "suspect": "suspected",
    "confirme": "confirmed",
    "decede": "deceased"
}

def remove_accents(series):
    """Standardizes text by stripping French accents and title-casing names."""
    return (series.astype(str)
            .str.normalize('NFKD')
            .str.encode('ascii', errors='ignore')
            .str.decode('utf-8')
            .str.strip()
            .str.title())

def clean_and_sync():
    print("🧹 Starting bilingual data cleaning and transformation pipeline...")
    
    # --- Target: Only INSP SitRep Processed Files ---
    search_path = os.path.join("data_test", "*insp_sitrep*.csv")
    sitrep_files = glob.glob(search_path)
    
    if sitrep_files:
        for file_path in sitrep_files:
            # Derive clean database table name
            filename = os.path.basename(file_path).replace(".csv", "").lower()
            table_name = filename.replace("__", "_")
            
            print(f"📦 Processing: {file_path} -> Table: '{table_name}'")
            
            # Load CSV
            df = pd.read_csv(file_path)
            
            # 1. Column Casing & Mapping (French -> English standard)
            df.columns = df.columns.str.lower().str.strip()
            df = df.rename(columns=COLUMN_TRANSLATIONS)
            
            # 2. Normalize Geographic names (drop 'Zone de sante' prefix and normalize accents)
            zone_cols = [c for c in df.columns if 'zone' in c or 'health_zone' in c]
            if zone_cols:
                df[zone_cols[0]] = df[zone_cols[0]].astype(str).str.replace(r"(?i)zone de sant(e|é)\s*", "", regex=True)
                df[zone_cols[0]] = remove_accents(df[zone_cols[0]])
            
            # 3. Clean and sanitize dates (handling brackets like ']' and formatting)
            if 'date' in df.columns:
                df['date'] = df['date'].astype(str).str.replace(r'[\[\]\'"\s]', '', regex=True)
                df['date'] = pd.to_datetime(df['date'], errors='coerce')
                
                if zone_cols:
                    df = df.sort_values(by=[zone_cols[0], 'date'])
            
            # 4. Standardize Categorical Column values if bilingual data is present
            for col in df.columns:
                if df[col].dtype == 'object' and (not zone_cols or col != zone_cols[0]):
                    cleaned_series = df[col].astype(str).str.lower().str.strip()
                    cleaned_series = (cleaned_series.str.normalize('NFKD')
                                      .str.encode('ascii', errors='ignore')
                                      .str.decode('utf-8'))
                    if cleaned_series.isin(STATUS_TRANSLATIONS.keys()).any():
                        df[col] = cleaned_series.replace(STATUS_TRANSLATIONS).str.title()

            # DB INSERTION: Write only 'insp_sitrep' processed tables
            df.to_sql(table_name, engine, if_exists='replace', index=False)
            print(f"✔ '{table_name}' table written/updated in the database.")
    else:
        print("❌ Error: No CSV files matching '*insp_sitrep*.csv' found in data_test/")

    print("🎉 Ingestion & Database sync complete!")

if __name__ == "__main__":
    clean_and_sync()
