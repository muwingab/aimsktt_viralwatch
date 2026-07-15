import os
import pandas as pd
import numpy as np

try:
    import geopandas as gpd
    GEOPANDAS_AVAILABLE = True
except ImportError:
    GEOPANDAS_AVAILABLE = False

COLUMN_TRANSLATIONS = {
    "date_notification": "date",
    "date_rapport": "date",
    "jour": "date",
    "zone_de_sante": "health_zone",
    "zone_sante": "health_zone",
    "nom": "health_zone",
    "nom_zone": "health_zone",
    "province": "province",
    "cas_confirmes": "confirmed_cases",
    "cas_suspects": "suspected_cases",
    "deces": "deaths",
    "gueris": "recovered"
}

STATUS_TRANSLATIONS = {
    "oui": "yes", "non": "no", "vrai": "true", "faux": "false",
    "suspect": "suspected", "confirme": "confirmed", "decede": "deceased"
}

def remove_accents(series):
    """Standardizes text by stripping French accents and title-casing names."""
    return (series.astype(str)
            .str.normalize('NFKD')
            .str.encode('ascii', errors='ignore')
            .str.decode('utf-8')
            .str.strip()
            .str.title())

def clean_dataframe(df):
    """Applies standard data cleaning and normalization to DataFrames."""
    # 1. Clean and Map Column Headers
    df.columns = df.columns.str.lower().str.strip()
    df = df.rename(columns=COLUMN_TRANSLATIONS)
    
    # 2. Process & Standardize Geographic Names
    zone_cols = [c for c in df.columns if 'zone' in c or 'health_zone' in c]
    if zone_cols:
        col = zone_cols[0]
        # Drop prefixes and standardize accents
        df[col] = df[col].astype(str).str.replace(r"(?i)zone de sant(e|é)\s*", "", regex=True)
        df[col] = remove_accents(df[col])
    
    # Standardize Province columns
    prov_cols = [c for c in df.columns if 'province' in c]
    if prov_cols:
        col = prov_cols[0]
        df[col] = remove_accents(df[col])
    
    # 3. Clean dates
    if 'date' in df.columns:
        df['date'] = df['date'].astype(str).str.replace(r'[\[\]\'"\s]', '', regex=True)
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        if zone_cols:
            df = df.sort_values(by=[zone_cols[0], 'date'])
            
    # 4. Standardize Categorical Column values
    for col in df.columns:
        if df[col].dtype == 'object' and col not in zone_cols and col not in prov_cols:
            cleaned_series = df[col].astype(str).str.lower().str.strip()
            cleaned_series = (cleaned_series.str.normalize('NFKD')
                              .str.encode('ascii', errors='ignore')
                              .str.decode('utf-8'))
            if cleaned_series.isin(STATUS_TRANSLATIONS.keys()).any():
                df[col] = cleaned_series.replace(STATUS_TRANSLATIONS).str.title()
                
    # 5. Handle "ND" (Non Disponible) to proper Numeric Nulls
    numeric_candidates = ['confirmed_cases', 'suspected_cases', 'deaths', 'recovered', 'cases', 'value']
    for col in df.columns:
        if col in numeric_candidates or df[col].astype(str).str.upper().isin(['ND', 'N/D', 'NULL']).any():
            df[col] = df[col].astype(str).replace(r'(?i)\b(nd|n/d|null|nan)\b', np.nan, regex=True)
            df[col] = pd.to_numeric(df[col], errors='coerce')

    return df

def process_shapefile(file_path):
    """Loads a shapefile using Geopandas and simplifies coordinates for standard database storage."""
    if not GEOPANDAS_AVAILABLE:
        print("⚠️ Warning: geopandas is not installed. Shapefile fallback to pandas DBF parse.")
        df = pd.read_csv(file_path.replace(".shp", ".dbf"), errors="ignore")
        return clean_dataframe(df)
        
    print(f"🗺️ Spatial conversion: Reading {os.path.basename(file_path)}")
    gdf = gpd.read_file(file_path)
    
    if 'geometry' in gdf.columns:
        gdf['wkt_geometry'] = gdf['geometry'].apply(lambda geom: geom.wkt if geom else None)
        gdf = gdf.drop(columns=['geometry'])
        
    return clean_dataframe(pd.DataFrame(gdf))
