# Import the required libraries
import json
import os
from datetime import datetime, timedelta
from io import StringIO

import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
roaster_url = os.getenv('ROASTER_URL')
pto_url = os.getenv('PTO_URL')
username = os.getenv('USERNAME')
password = os.getenv('PASSWORD')

# Link style sheet file, style.css
st.markdown(f'<style>{open("style.css").read()}</style>', unsafe_allow_html=True)

# Load employees data
employees_df = pd.DataFrame(pd.read_csv(roaster_url))

# Load PTO data from the quotes.madwell API
USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36'
HEADERS = {'User-Agent': USER_AGENT}
def fetch_pto_data(pto_url, username, password):
    try:
        response = requests.get(pto_url, auth=(username, password), headers=HEADERS)
        response.raise_for_status()
        pto_calendar_json = response.text
        pto_calendar = json.loads(pto_calendar_json)["requestList"]
        return pto_calendar
    except requests.exceptions.HTTPError as http_err:
        st.error(f"HTTP error occurred: {http_err}")
    except requests.exceptions.RequestException as req_err:
        st.error(f"Request error occurred: {req_err}")
    except json.JSONDecodeError as json_err:
        st.error(f"JSON decode error occurred: {json_err}")
    return []
pto_calendar = fetch_pto_data(pto_url, username, password)

# Load signin data from the uploaded CSV file(s)
signin_data = 'Name,Site,Group,"In time"'
lines = 1
start_date_of_week = datetime.now()
end_date_of_week = datetime.now()
st.title("Madwell Signin App")
uploaded_files = st.file_uploader("Choose CSV file(s) of weekly signin data. [ Sunday to Saturday ]", accept_multiple_files=True, type="csv")
if uploaded_files:
    combined_df = pd.DataFrame()

    for i, uploaded_file in enumerate(uploaded_files):
        # Read the CSV file
        if i == 0:
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_csv(uploaded_file, skiprows=1, header=None)
            df.columns = combined_df.columns

        combined_df = pd.concat([combined_df, df], ignore_index=True)

    signin_data = combined_df.to_csv(index=False)

    # Extract the 'In time' column and convert to datetime
    date_format = '%m/%d/%Y %I:%M %p'
    combined_df['In time'] = pd.to_datetime(combined_df['In time'], format=date_format)

    # Set the start and end date for the week
    min_date = combined_df['In time'].min()
    max_date = combined_df['In time'].max()
    if min_date.weekday() == 6:
        min_date = min_date + timedelta(days=1)

    start_date_of_week = (min_date - timedelta(days=min_date.weekday() + 1)).replace(hour=1, minute=0, second=0, microsecond=0)
    end_date_of_week = start_date_of_week + timedelta(days=6)
    lines = len(combined_df)
    st.success(f"Successfully uploaded {lines} lines of data.")
else:
    st.warning("Waiting for CSV file(s) to be uploaded...")

signin_df = pd.read_csv(StringIO(signin_data), index_col=False)
date_range = pd.date_range(start=start_date_of_week, end=end_date_of_week)

# Process the signin data
def process_signin(signin_df, date_range, employees_df):
    signin_summary = []

    for index, row in employees_df.iterrows():
        name = row['FULL_NAME']
        pto_name = row['JW_NAME']
        dept = row['DEPARTMENT']
        office = row['OFFICE']
        required_days = row['REQUIRED_DAYS']
        pto_count = 0

        # Get the present days
        present_days = []
        present_dates = []
        present_day_names = []
        for date in date_range:
            date_str = date.strftime('%a %m/%d/%Y').upper()
            if name in signin_df['Name'].values:
                rows = signin_df.loc[signin_df['Name'] == name]
                present_days = rows.to_dict('records')
                present_days = [record for record in present_days if datetime.strptime(record['In time'], '%m/%d/%Y %I:%M %p').strftime('%a').upper() not in ['SUN', 'MON', 'FRI', 'SAT']]
                present_dates = [record["In time"] for record in present_days if datetime.strptime(record['In time'], '%m/%d/%Y %I:%M %p').strftime('%a').upper() not in ['SUN', 'MON', 'FRI', 'SAT']]
                present_day_names = [datetime.strptime(row['In time'], '%m/%d/%Y %I:%M %p').strftime('%a').upper() for row in present_days]
        present_day_names = sorted(present_day_names, key=lambda x: ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'].index(x))
        present_day_names = [day for day in present_day_names if day not in ['SUN', 'MON', 'FRI', 'SAT']]
        # remove duplicates
        present_day_names = list(dict.fromkeys(present_day_names))
        if len(present_day_names) == 0:
            present_day_names = ['NO SIGNIN']

        # Count the number of PTOs that fall within Tuesday, Wednesday, and Thursday of the date range
        pto_dates = []
        for pto in pto_calendar:
            if pto['name'] == pto_name:
                leave_dates = pto['leaveDates']
                for leave_date in leave_dates:
                    leave_date = datetime.strptime(leave_date, '%Y-%m-%d').replace(hour=1, minute=0, second=0, microsecond=0)

                    if leave_date.weekday() in [1, 2, 3] and leave_date in date_range:
                        pto_count += 1
                        pto_dates.append(leave_date)
                        continue

        # Add the summary to the row list
        updated_required_days = max(0, required_days - pto_count)
        sorted_pto_days = sorted([date.strftime('%a').upper() for date in pto_dates])

        signin_summary.append({
            'NAME': name,
            'DEPT': dept,
            'OFFICE': office,
            'STATUS': "X" if (len(present_days) / max(1, updated_required_days)) < 1 else "O",
            'SIGNIN DETAILS': f"{min(updated_required_days, len(present_days))} / {updated_required_days} [ PTOs={pto_count} ]",
            'SIGNIN DAYS': '/'.join(present_day_names),
            'PTO DAYS': ', '.join(sorted_pto_days) if len(sorted_pto_days) > 0 else 'N/A',
            'USED PTOs': len(sorted_pto_days),
            'PRESENT': sorted([present_date[:10] for present_date in present_dates]),
        })
    return signin_summary

signin_summary = process_signin(signin_df, date_range, employees_df)

# Convert the summary to a DataFrame
signin_table = pd.DataFrame(signin_summary)

# Filter out rows where required_days is 0
signin_table = signin_table[signin_table['SIGNIN DETAILS'].apply(lambda x: int(x.split(' ')[2]) != 0)]

# Sort the DataFrame by 'OFFICE', 'DEPT', and 'NAME'
signin_table = signin_table.sort_values(by=['OFFICE', 'DEPT', 'NAME'])

# Define a function to apply the background color to the entire row
def highlight_row(row):
    present_days = int(row['SIGNIN DETAILS'].split(' ')[0])
    required_days = int(row['SIGNIN DETAILS'].split(' ')[2])
    bg_color = 'background-color: rgba(50,0,0,0.5); text-align: center;' if present_days < required_days else ''
    align = 'text-align: center'

    return [bg_color] * len(row)

# Apply the function to the entire DataFrame
styled_signin_table = signin_table.style.apply(highlight_row, axis=1)

# Render the signin data
if lines > 1:
    st.subheader("Weekly Signin Data")
    st.write("[ Week of ", start_date_of_week.strftime('%m/%d/%Y'), "-", end_date_of_week.strftime('%m/%d/%Y'), " ]")
    st.dataframe(styled_signin_table, hide_index=True)
