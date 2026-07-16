import pandas as pd
import numpy as np

def calculate_days_since_first_case_no_header(filepath):
    # 1. Load the CSV explicitly telling Pandas there are NO headers
    # This prevents the first row of data from being treated as column names
    df = pd.read_csv(filepath, header=None)
    
    # 2. Assign explicit column names based on the known format:
    # Column 0: Health Zone, Column 1: Date, Column 2: Cumulative Cases
# 2. Assign explicit column names
# 2. Assign explicit column names
    df.columns = ['health_zone', 'date', 'value']
    
    # 3. Clean BOTH columns to remove rogue brackets, quotes, or spaces
    df['date'] = df['date'].astype(str).str.strip("[]'\" ")
    df['value'] = df['value'].astype(str).str.strip("[]'\" ")
    
    # Convert them to their correct data types
    df['date'] = pd.to_datetime(df['date'])
    df['value'] = pd.to_numeric(df['value'], errors='coerce').fillna(0).astype(int)
    
    # 4. Filter for rows where cumulative cases are greater than 0
    positive_cases = df[df['value'] > 0]
    
    # 5. Find the absolute first date each health zone reported a case
    first_case_dates = positive_cases.groupby('health_zone')['date'].min().reset_index()
    first_case_dates.rename(columns={'date': 'first_case_date'}, inplace=True)
    
    # 6. Merge the baseline onset dates back into your main dataframe
    df = pd.merge(df, first_case_dates, on='health_zone', how='left')
    
    # 7. Calculate the days delta
    df['days_since_first_case'] = (df['date'] - df['first_case_date']).dt.days
    
    # 8. Clean up edge cases (no cases yet, or dates before patient zero)
    df['days_since_first_case'] = df['days_since_first_case'].fillna(0)
    df.loc[df['days_since_first_case'] < 0, 'days_since_first_case'] = 0
    
    # Convert to integer
    df['days_since_first_case'] = df['days_since_first_case'].astype(int)
    
    # Drop the temporary helper column
    df.drop(columns=['first_case_date'], inplace=True)
    
    return df

csv_file_path = r"C:\Users\STUDENT\OneDrive\Desktop\KTT Fellowship\ViralWatch Project\aimsktt_viralwatch\ml\dataset\insp_sitrep__cumulative_confirmed_cases.csv"

# 2. Execute the function and store the result in a new dataframe
feature_df = calculate_days_since_first_case_no_header(csv_file_path)

output_filepath = r"C:\Users\STUDENT\OneDrive\Desktop\KTT Fellowship\ViralWatch Project\aimsktt_viralwatch\ml\dataset\days_since_first_case.csv"
feature_df = calculate_days_since_first_case_no_header(csv_file_path)

# 4. Create the final CSV file
# We use index=False so Pandas doesn't write the row numbers (0, 1, 2...) as a new column
feature_df.to_csv(output_filepath, index=False)

print(f"Success! The new CSV file has been saved to: {output_filepath}")