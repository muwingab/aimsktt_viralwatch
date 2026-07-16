import os
import re
from pathlib import Path
import pandas as pd
import numpy as np

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


def join_insp_sitrep_csvs(input_dir: Path | str, output_path: Path | str) -> pd.DataFrame:
    """
    Join ALL INSP SitRep CSV files on (nom, date) into a single wide table.
    Gracefully handles merging without losing 'nd' values by dynamically renaming them.
    """
    input_dir = Path(input_dir)
    output_path = Path(output_path)

    print(f"📂 Searching for files in: {input_dir.resolve()}")
    csv_files = sorted(input_dir.glob("insp_sitrep*.csv"))
    
    if not csv_files:
        print("⚠️ Warning: No files starting with 'insp_sitrep*' found!")
        return pd.DataFrame(columns=["nom", "date"])

    print(f"📈 Found {len(csv_files)} files to merge.")
    frames: list[pd.DataFrame] = []

    for csv_path in csv_files:
        try:
            df = pd.read_csv(csv_path)
            df.columns = df.columns.str.lower().str.strip()

            cols_to_drop = [col for col in df.columns if col in ['unnamed: 0', 'index']]
            if cols_to_drop:
                df = df.drop(columns=cols_to_drop)

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
                continue

            df['date'] = df['date'].astype(str).str.strip()
            value_columns = [col for col in df.columns if col not in ['nom', 'date']]
            
            if not value_columns:
                df[f"has_data_{csv_path.stem}"] = 1
                value_columns = [f"has_data_{csv_path.stem}"]

            file_metric_prefix = csv_path.stem.split("__")[1] if len(csv_path.stem.split("__")) >= 2 else csv_path.stem

            for col in value_columns:
                if col in ['value', 'cases', 'count', 'valeur', 'nd']:
                    unique_col_name = f"{file_metric_prefix}_{col}" if col == 'nd' else file_metric_prefix
                    df.rename(columns={col: unique_col_name}, inplace=True)

            frames.append(df)
        except Exception as file_err:
            print(f"      ❌ Failed to parse {csv_path.name}: {file_err}")

    if not frames:
        return pd.DataFrame(columns=["nom", "date"])

    print(f"🔄 Merging {len(frames)} dataframes...")
    merged = frames[0]
    for i, frame in enumerate(frames[1:], start=1):
        merged = pd.merge(
            merged, 
            frame, 
            on=["nom", "date"], 
            how="outer", 
            suffixes=('', f'_dup_{i}')
        )

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        merged.to_csv(output_path, index=False)
        print(f"💾 Saved merged table to file: {output_path}")
    except Exception as save_err:
        print(f"⚠️ Could not write output file to disk: {save_err}")

    return merged


def _read_flowminder_frame(csv_path: Path) -> pd.DataFrame | None:
    """Read one Flowminder CSV as a two-column geography/value frame."""
    with csv_path.open("r", encoding="utf-8") as handle:
        first_line = handle.readline().strip().split(",")

    header_row = (
        len(first_line) >= 2
        and first_line[0].strip().lower() in {"nom", "zone_de_sante", "zone_sante", "zone"}
        and first_line[1].strip().lower() in {"value", "inflow", "outflow", "date"}
    )

    if header_row:
        frame = pd.read_csv(csv_path)
    else:
        frame = pd.read_csv(csv_path, header=None)
        if frame.shape[1] < 2:
            return None
        frame = frame.iloc[:, :2].copy()
        frame.columns = ["nom", "value"]

    if frame.shape[1] < 2:
        return None

    frame = frame.iloc[:, :2].copy()
    frame.columns = ["nom", "value"]
    return frame


def join_flowminder_csvs(input_dir: Path | str, output_path: Path | str) -> pd.DataFrame:
    """Join Flowminder files on geography key ('nom') to build a wide table."""
    input_dir = Path(input_dir)
    output_path = Path(output_path)

    csv_files = sorted(input_dir.glob("flowminder*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No flowminder*.csv files found in {input_dir}")

    frames: list[pd.DataFrame] = []
    skipped_files: list[str] = []

    for csv_path in csv_files:
        frame = _read_flowminder_frame(csv_path)
        if frame is None:
            print(f"Skipping {csv_path.name}: expected at least 2 columns")
            skipped_files.append(csv_path.name)
            continue

        feature_name = csv_path.stem
        feature_frame = frame[["nom", "value"]].copy()
        feature_frame.rename(columns={"value": feature_name}, inplace=True)
        frames.append(feature_frame)

    if not frames:
        raise RuntimeError(f"No frames to merge. Skipped files: {skipped_files}")

    merged = frames[0]
    join_col = "nom"
    for frame in frames[1:]:
        merged = pd.merge(merged, frame, on=join_col, how="outer")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(output_path, index=False)
    return merged


def join_worldpop_csvs(input_dir: Path | str, output_path: Path | str) -> pd.DataFrame:
    """Finds WorldPop files (count and density) and merges them into a wide table."""
    input_dir = Path(input_dir)
    output_path = Path(output_path)

    csv_files = list(input_dir.glob("*worldpop*.csv"))
    
    count_file = None
    density_file = None

    for f in csv_files:
        name_lower = f.name.lower()
        if "density" in name_lower:
            density_file = f
        elif "count" in name_lower or "pop" in name_lower:
            count_file = f

    if not count_file and not density_file:
        raise FileNotFoundError(f"No WorldPop count or density files found in {input_dir}")

    if count_file:
        print(f"📈 Reading WorldPop counts from: {count_file.name}")
        df_count = pd.read_csv(count_file)
        df_count.columns = df_count.columns.str.lower().str.strip()
        df_count = df_count.rename(columns={
            "zone_sante": "nom", "zone_de_sante": "nom", "health_zone": "nom", "nom_zone": "nom",
            "value": "count", "population": "count"
        })
        df_count = df_count[["nom", "count"]].copy()
    else:
        df_count = pd.DataFrame(columns=["nom", "count"])

    if density_file:
        print(f"📈 Reading WorldPop density from: {density_file.name}")
        df_density = pd.read_csv(density_file)
        df_density.columns = df_density.columns.str.lower().str.strip()
        df_density = df_density.rename(columns={
            "zone_sante": "nom", "zone_de_sante": "nom", "health_zone": "nom", "nom_zone": "nom",
            "value": "density"
        })
        df_density = df_density[["nom", "density"]].copy()
    else:
        df_density = pd.DataFrame(columns=["nom", "density"])

    if not df_count.empty and not df_density.empty:
        merged = pd.merge(df_count, df_density, on="nom", how="outer")
    elif not df_count.empty:
        merged = df_count
        merged["density"] = np.nan
    else:
        merged = df_density
        merged["count"] = np.nan

    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(output_path, index=False)
    print(f"💾 Merged WorldPop table created: {output_path}")
    
    return merged
