import json
import os
from datetime import datetime, timedelta
from typing import List, Dict

import pandas as pd
from pandas.io.formats.style import Styler
import requests
import streamlit as st
from dotenv import load_dotenv

USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36'
HEADERS = {'User-Agent': USER_AGENT}
DATE_FORMAT = '%m/%d/%Y %I:%M %p'

def load_environment_variables():
    load_dotenv()
    return {
        'roaster_url': os.getenv('ROASTER_URL'),
        'pto_url': os.getenv('PTO_URL'),
        'username': os.getenv('USERNAME'),
        'password': os.getenv('PASSWORD')
    }

def load_css(filename: str):
    st.markdown(f'<style>{open(filename).read()}</style>', unsafe_allow_html=True)

def fetch_pto_data(pto_url: str, username: str, password: str) -> List[Dict]:
    try:
        response = requests.get(pto_url, auth=(username, password), headers=HEADERS)
        response.raise_for_status()
        pto_calendar_json = response.text
        return json.loads(pto_calendar_json)["requestList"]
    except (requests.exceptions.HTTPError, requests.exceptions.RequestException, json.JSONDecodeError) as err:
        st.error(f"Error occurred while fetching PTO data: {err}")
        return []

def combine_csv_files(uploaded_files) -> pd.DataFrame:
    combined_df = pd.DataFrame()
    for i, uploaded_file in enumerate(uploaded_files):
        df = pd.read_csv(uploaded_file, skiprows=1 if i > 0 else 0, header=None if i > 0 else 'infer')
        if i > 0:
            df.columns = combined_df.columns
        combined_df = pd.concat([combined_df, df], ignore_index=True)
    return combined_df

def calculate_date_range(combined_df: pd.DataFrame) -> tuple:
    combined_df['In time'] = pd.to_datetime(combined_df['In time'], format=DATE_FORMAT)
    min_date = combined_df['In time'].min()
    if min_date.weekday() == 6:
        min_date += timedelta(days=1)
    start_date = (min_date - timedelta(days=min_date.weekday() + 1)).replace(hour=1, minute=0, second=0, microsecond=0)
    end_date = start_date + timedelta(days=6)
    return start_date, end_date

def load_signin_data(uploaded_files) -> tuple:
    if not uploaded_files:
        st.warning("Waiting for CSV file(s) to be uploaded...")
        return pd.DataFrame(), datetime.now(), datetime.now()
    
    combined_df = combine_csv_files(uploaded_files)
    start_date, end_date = calculate_date_range(combined_df)
    
    st.success(f"Successfully uploaded {len(combined_df)} lines of data.")
    return combined_df, start_date, end_date

def get_pto_dates(pto_calendar: List[Dict], pto_name: str, date_range: pd.DatetimeIndex) -> List[datetime]:
    pto_dates = []
    for pto in pto_calendar:
        if pto['name'] == pto_name:
            for leave_date in pto['leaveDates']:
                leave_date = datetime.strptime(leave_date, '%Y-%m-%d').replace(hour=1, minute=0, second=0, microsecond=0)
                if leave_date.weekday() in [1, 2, 3] and leave_date in date_range:
                    pto_dates.append(leave_date)
    return pto_dates

def process_employee_signin(row, signin_df, date_range, pto_calendar) -> Dict:
    name, pto_name, dept, office, required_days = row['FULL_NAME'], row['JW_NAME'], row['DEPARTMENT'], row['OFFICE'], row['REQUIRED_DAYS']
    
    present_days = signin_df[signin_df['Name'] == name]
    present_days = present_days[present_days['In time'].dt.strftime('%a').isin(['Tue', 'Wed', 'Thu'])]
    present_dates = list(set(present_days['In time'].dt.strftime('%m/%d/%Y').tolist()))
    present_day_names = sorted(set(present_days['In time'].dt.strftime('%a')))
    
    pto_dates = get_pto_dates(pto_calendar, pto_name, date_range)
    pto_count = len(pto_dates)
    updated_required_days = max(0, required_days - pto_count)
    present_count = min(updated_required_days, len(present_days))
    
    return {
        'NAME': name,
        'DEPT': dept,
        'OFFICE': office,
        'STATUS': "X" if present_count < updated_required_days else "O",
        'SIGNIN DETAILS': f"{present_count} / {updated_required_days} [ PTOs={pto_count} ]",
        'SIGNIN DAYS': '/'.join(present_day_names) if present_day_names else 'NO SIGNIN',
        'PTO DAYS': ', '.join(sorted([date.strftime('%a') for date in pto_dates])) if pto_dates else 'N/A',
        'USED PTOs': len(pto_dates),
        'PRESENT': sorted(present_dates),
    }

def process_signin(signin_df: pd.DataFrame, date_range: pd.DatetimeIndex, employees_df: pd.DataFrame, pto_calendar: List[Dict]) -> List[Dict]:
    signin_summary = [process_employee_signin(row, signin_df, date_range, pto_calendar) for _, row in employees_df.iterrows()]
    return signin_summary

def create_styled_dataframe(signin_summary: List[Dict]) -> Styler:
    df = pd.DataFrame(signin_summary)
    df = df[df['SIGNIN DETAILS'].apply(lambda x: int(x.split(' ')[2]) != 0)]
    df = df.sort_values(by=['OFFICE', 'DEPT', 'NAME'])
    
    def highlight_row(row):
        signin_details = row['SIGNIN DETAILS'].split(' ')
        present_days = int(signin_details[0])
        required_days = int(signin_details[2])
        return ['background-color: rgba(50,0,0,0.5); text-align: center;' if present_days < required_days else ''] * len(row)
    
    return df.style.apply(highlight_row, axis=1)

def main():
    st.title("Madwell Signin App")
    load_css("style.css")
    
    env_vars = load_environment_variables()
    employees_df = pd.read_csv(env_vars['roaster_url'])
    pto_calendar = fetch_pto_data(env_vars['pto_url'], env_vars['username'], env_vars['password'])
    
    uploaded_files = st.file_uploader("Choose CSV file(s) of weekly signin data. [ Sunday to Saturday ]", accept_multiple_files=True, type="csv")
    
    signin_df, start_date, end_date = load_signin_data(uploaded_files)
    
    if not signin_df.empty:
        date_range = pd.date_range(start=start_date, end=end_date)
        signin_summary = process_signin(signin_df, date_range, employees_df, pto_calendar)
        styled_signin_table = create_styled_dataframe(signin_summary)
        
        st.subheader("Weekly Signin Data")
        st.write(f"[ Week of {start_date.strftime('%m/%d/%Y')} - {end_date.strftime('%m/%d/%Y')} ]")
        st.dataframe(styled_signin_table, hide_index=True)

if __name__ == "__main__":
    main()
