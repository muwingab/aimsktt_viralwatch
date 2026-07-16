import os
import re
from pathlib import Path
import pandas as pd
import numpy as np

# Try to import geopandas for full GIS capabilities
try:
    import geopandas as gpd
    GEOPANDAS_AVAILABLE = True
except ImportError:
    GEOPANDAS_AVAILABLE = False

# Try to import pyshp (shapefile) for lightweight shapefile parsing
try:
    import shapefile
    PYSHP_AVAILABLE = True
except ImportError:
    PYSHP_AVAILABLE = False

# Try to import dbfread as a last resort fallback
try:
    from dbfread import DBF
    DBFREAD_AVAILABLE = True
except ImportError:
    DBFREAD_AVAILABLE = False

COLUMN_TRANSLATIONS = {
    "date_notification": "date",
    "date_rapport": "date",
    "jour": "date",
    "zone_de_sante": "health_zone",
    "zone_sante": "health_zone",
    "nom_zone": "health_zone",
    "nom_sante": "health_zone",
    "nom": "health_zone",
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


def remove_accents(series: pd.Series) -> pd.Series:
    """Standardizes text by stripping French accents and title-casing names."""
    return (series.astype(str)
            .str.normalize('NFKD')
            .str.encode('ascii', errors='ignore')
            .str.decode('utf-8')
            .str.strip()
            .str.title())


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Applies standard data cleaning and normalization to DataFrames."""
    df.columns = df.columns.str.lower().str.strip()
    df = df.rename(columns=COLUMN_TRANSLATIONS)
    
    zone_cols = [c for c in df.columns if 'zone' in c or 'health_zone' in c]
    if zone_cols:
        col = zone_cols[0]
        df[col] = df[col].astype(str).str.replace(r"(?i)zone de sant(e|é)\s*", "", regex=True)
        df[col] = remove_accents(df[col])
    
    prov_cols = [c for c in df.columns if 'province' in c]
    if prov_cols:
        col = prov_cols[0]
        df[col] = remove_accents(df[col])
    
    if 'date' in df.columns:
        df['date'] = df['date'].astype(str).str.replace(r'[\[\]\'"\s]', '', regex=True)
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        if zone_cols:
            df = df.sort_values(by=[zone_cols[0], 'date'])
            
    for col in df.columns:
        if df[col].dtype == 'object' and col not in zone_cols and col not in prov_cols:
            cleaned_series = df[col].astype(str).str.lower().str.strip()
            cleaned_series = (cleaned_series.str.normalize('NFKD')
                              .str.encode('ascii', errors='ignore')
                              .str.decode('utf-8'))
            if cleaned_series.isin(STATUS_TRANSLATIONS.keys()).any():
                df[col] = cleaned_series.replace(STATUS_TRANSLATIONS).str.title()
                
    numeric_candidates = ['confirmed_cases', 'suspected_cases', 'deaths', 'recovered', 'cases', 'value']
    for col in df.columns:
        if col in numeric_candidates or df[col].astype(str).str.upper().isin(['ND', 'N/D', 'NULL']).any():
            df[col] = df[col].astype(str).replace(r'(?i)\b(nd|n/d|null|nan)\b', np.nan, regex=True)
            df[col] = pd.to_numeric(df[col], errors='coerce')

    return df


def process_shapefile(file_path: str) -> pd.DataFrame:
    """Loads a shapefile using Geopandas, pyshp (fallback), or dbfread."""
    if GEOPANDAS_AVAILABLE:
        print(f"🗺️ Spatial conversion: Reading spatial geometry from {os.path.basename(file_path)}")
        gdf = gpd.read_file(file_path)
        if 'geometry' in gdf.columns:
            gdf['wkt_geometry'] = gdf['geometry'].apply(lambda geom: geom.wkt if geom else None)
            gdf = gdf.drop(columns=['geometry'])
        return clean_dataframe(pd.DataFrame(gdf))
        
    elif PYSHP_AVAILABLE:
        print(f"📄 Reading Shapefile using lightweight 'pyshp': {os.path.basename(file_path)}")
        try:
            sf = shapefile.Reader(file_path)
            fields = [f[0] for f in sf.fields][1:]
            records = [list(r) for r in sf.records()]
            df = pd.DataFrame(columns=fields, data=records)
            geoms = [s.points for s in sf.shapes()]
            df = df.assign(coordinates_raw=geoms)
            return clean_dataframe(df)
        except Exception as e:
            print(f"⚠️ pyshp failed to process shapefile: {e}. Attempting DBF parsing...")
            
    print("⚠️ Geopandas/pyshp unavailable. Attempting tabular attribute recovery...")
    dbf_path = file_path.replace(".shp", ".dbf").replace(".SHP", ".dbf")
    
    if DBFREAD_AVAILABLE and os.path.exists(dbf_path):
        print(f"📄 Reading tabular attributes from DBF: {os.path.basename(dbf_path)}")
        dbf = DBF(dbf_path, load=True)
        df = pd.DataFrame(iter(dbf))
        return clean_dataframe(df)
    else:
        print("❌ Error: Missing parser dependencies. Install pyshp with: pip install pyshp")
        return pd.DataFrame(columns=["health_zone", "province"])


def join_insp_sitrep_csvs(input_dir: Path | str, output_path: Path | str) -> pd.DataFrame:
    """
    Join ALL INSP SitRep CSV files on (nom, date) into a single wide table.
    Gracefully returns an empty DataFrame if no files are found.
    """
    input_dir = Path(input_dir)
    output_path = Path(output_path)

    print(f"📂 Searching for files in: {input_dir.resolve()}")
    csv_files = sorted(input_dir.glob("insp_sitrep*.csv"))
    
    # 🔎 LOGGING: Check if files were matched
    if not csv_files:
        print("⚠️ Warning: No files starting with 'insp_sitrep*' found!")
        # Print directory contents to help troubleshoot
        if input_dir.exists():
            print(f"Directory contents: {[f.name for f in input_dir.iterdir()]}")
        return pd.DataFrame(columns=["nom", "date"])

    print(f"📈 Found {len(csv_files)} files to merge.")
    frames: list[pd.DataFrame] = []

    for csv_path in csv_files:
        print(f"   ↳ Reading file: {csv_path.name}")
        try:
            df = pd.read_csv(csv_path)
            df.columns = df.columns.str.lower().str.strip()

            rename_map = {}
            for col in df.columns:
                if col in ['nom', 'zone_sante', 'zone_de_sante', 'nom_zone', 'health_zone']:
                    rename_map[col] = 'nom'
                elif col in ['date', 'jour', 'date_rapport', 'date_notification']:
                    rename_map[col] = 'date'
            
            df = df.rename(columns=rename_map)

            if 'nom' not in df.columns and len(df.columns) > 0:
                df.rename(columns={df.columns[0]: 'nom'}, inplace=True)
            if 'date' not in df.columns and len(df.columns) > 1:
                df.rename(columns={df.columns[1]: 'date'}, inplace=True)

            if 'nom' not in df.columns or 'date' not in df.columns:
                print(f"      ⚠️ Missing headers. Columns found: {list(df.columns)}")
                continue

            df['date'] = df['date'].astype(str).str.strip()
            value_columns = [col for col in df.columns if col not in ['nom', 'date']]
            
            if not value_columns:
                df[f"has_data_{csv_path.stem}"] = 1
                value_columns = [f"has_data_{csv_path.stem}"]

            for col in value_columns:
                if col in ['value', 'cases', 'count', 'valeur']:
                    metric_name = csv_path.stem.split("__")[1] if len(csv_path.stem.split("__")) >= 2 else csv_path.stem
                    df.rename(columns={col: metric_name}, inplace=True)

            frames.append(df)
        except Exception as file_err:
            print(f"      ❌ Failed to parse {csv_path.name}: {file_err}")

    if not frames:
        print("⚠️ No valid data frames could be compiled from the matching files.")
        return pd.DataFrame(columns=["nom", "date"])

    print(f"🔄 Merging {len(frames)} dataframes...")
    merged = frames[0]
    for frame in frames[1:]:
        merged = pd.merge(merged, frame, on=["nom", "date"], how="outer")

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        merged.to_csv(output_path, index=False)
        print(f"💾 Saved merged table to file: {output_path}")
    except Exception as save_err:
        print(f"⚠️ Could not write output file to disk: {save_err}")

    return merged


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    input_dir = repo_root / "data" / "external" / "BDBV2026-Data" / "build" / "long"
    output_path = repo_root / "output" / "insp_sitrep_merged.csv"

    merged = join_insp_sitrep_csvs(input_dir, output_path)
    print(f"Wrote {len(merged)} rows to {output_path}")


if __name__ == "__main__":
    main()
