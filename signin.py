import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, TypedDict, Tuple

import hmac
import pandas as pd
from pandas import DataFrame, DatetimeIndex
from pandas.io.formats.style import Styler
import requests
import streamlit as st
from streamlit_dynamic_filters import DynamicFilters

### Constants ###
USER_AGENT: str = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36'
HEADERS: Dict[str, str] = {'User-Agent': USER_AGENT}
DATE_FORMAT: str = '%m/%d/%Y %I:%M %p'
STATUS_X_BG_COLOR = 'rgba(251, 231, 239, 0.5)'

### Type Definitions ###
class LeaveHourDetail(TypedDict):
    date: str
    dailyHours: str

class PTOData(TypedDict):
    employeeId: str
    name: str
    leaveType: str
    leaveTypeDescription: str
    status: str
    leaveRequest: str
    checksum: str
    startDate: str
    endDate: str
    comments: str
    leaveDates: List[str]
    vouchers: List
    leaveHours: int
    leaveHourDetails: List[LeaveHourDetail]
    absenceCodeReason: str
    ptoRegisterTypeCode: str

class SignInData(TypedDict):
    NAME: str
    DEPT: str
    OFFICE: str
    STATUS: str
    SIGNIN_DAYS: str
    ABSENT_DAYS: str
    SIGNIN_DETAILS: str
    PTO_DAYS: str
    USED_PTOs: int
    PRESENT: List[datetime]
    REQUIRED: int

### Authentication Functions ###
def password_entered() -> None:
    if hmac.compare_digest(st.session_state["password"], st.secrets["password"]):
        st.session_state["password_correct"] = True
        del st.session_state["password"]
    else:
        st.session_state["password_correct"] = False
        st.session_state["password"] = ""

def check_password() -> bool:
    if st.session_state.get("password_correct", False):
        return True
    st.text_input("Password", type="password", on_change=password_entered, key="password")
    if "password_correct" in st.session_state:
        st.error("😕 Password incorrect")
    return False

### Styling Function ###
def load_css(filename: str) -> None:
    st.markdown(f'<style>{open(filename).read()}</style>', unsafe_allow_html=True)

### Data Fetching Functions ###
def fetch_pto_data(pto_url: str, username: str, password: str) -> List[PTOData]:
    try:
        response: requests.Response = requests.get(pto_url, auth=(username, password), headers=HEADERS)
        response.raise_for_status()
        pto_calendar_json: str = response.text
        return json.loads(pto_calendar_json)["requestList"]
    except (requests.exceptions.HTTPError, requests.exceptions.RequestException, json.JSONDecodeError) as err:
        st.error(f"Error occurred while fetching PTO data: {err}")
        return []

def load_data() -> Tuple[DataFrame, List[PTOData]]:
    employees_df: DataFrame = pd.read_csv(st.secrets['roaster_url'])
    pto_calendar: List[PTOData] = fetch_pto_data(st.secrets['pto_url'], st.secrets['username'], st.secrets['password'])
    return employees_df, pto_calendar

### Signin CSV Processing Functions ###
def combine_csv_files(uploaded_files: List[bytes]) -> DataFrame:
    combined_df: DataFrame = DataFrame()
    for i, uploaded_file in enumerate(uploaded_files):
        df: DataFrame = pd.read_csv(uploaded_file, skiprows=1 if i > 0 else 0, header=None if i > 0 else 'infer')
        if i > 0:
            df.columns = combined_df.columns
        combined_df = pd.concat([combined_df, df], ignore_index=True)
    return combined_df

def calculate_date_range(combined_df: DataFrame) -> Tuple[datetime, datetime, bool, datetime, datetime]:
    combined_df['In time'] = pd.to_datetime(combined_df['In time'], format=DATE_FORMAT)
    min_date: datetime = combined_df['In time'].min()
    max_date: datetime = combined_df['In time'].max()
    more_than_7_days: bool = (max_date - min_date).days > 7
    start_date: datetime = (min_date - timedelta(days=min_date.weekday() + 1)).replace(hour=1, minute=0, second=0, microsecond=0)
    if min_date.weekday() == 6:
        start_date += timedelta(days=7)
    end_date: datetime = start_date + timedelta(days=6)
    return start_date, end_date, more_than_7_days, min_date, max_date

def load_signin_data(uploaded_files: List[bytes]) -> Tuple[DataFrame, datetime, datetime]:
    combined_df: DataFrame = combine_csv_files(uploaded_files)
    start_date, end_date, more_than_7_days, min_date, max_date = calculate_date_range(combined_df)
    if more_than_7_days:
        st.warning(f"Your data covers more than 7 days ({min_date.strftime('%m/%d/%Y')} - {max_date.strftime('%m/%d/%Y')}). Please upload only 7 days of data [Sun-Sat].")
        st.stop()
    else:
        st.success(f"Successfully uploaded {len(combined_df)} lines of data.")
    return combined_df, start_date, end_date

def process_uploaded_files(uploaded_files: List[Any]) -> Tuple[DataFrame, datetime, datetime]:
    signin_df, start_date, end_date = load_signin_data(uploaded_files)
    return signin_df, start_date, end_date

### Singin Data Processing Functions ###
def get_pto_dates(pto_calendar: List[PTOData], pto_name: str, date_range: DatetimeIndex) -> List[datetime]:
    pto_dates: List[datetime] = []
    for pto in pto_calendar:
        if pto['name'] == pto_name:
            for leave_date in pto['leaveDates']:
                leave_date: datetime = datetime.strptime(leave_date, '%Y-%m-%d').replace(hour=1, minute=0, second=0, microsecond=0)
                if leave_date.weekday() in [1, 2, 3] and leave_date in date_range:
                    pto_dates.append(leave_date)
    return pto_dates

def process_employee_signin(row: Dict[str, str], signin_df: DataFrame, date_range: DatetimeIndex, pto_calendar: List[PTOData]) -> SignInData:
    name: str = row['FULL_NAME']
    pto_name: str = row['JW_NAME']
    dept: str = row['DEPARTMENT']
    office: str = row['OFFICE']
    required_days: int = int(row['REQUIRED_DAYS'])
    
    day_order: List[str] = ['Tue', 'Wed', 'Thu']
    present_days: DataFrame = signin_df[signin_df['Name'] == name]
    present_days = present_days[present_days['In time'].dt.strftime('%a').isin(['Tue', 'Wed', 'Thu'])]
    present_dates: List[datetime] = list(set(present_days['In time'].dt.strftime('%m/%d/%Y').tolist()))
    present_day_names: List[str] = set(present_days['In time'].dt.strftime('%a'))
    present_day_names: List[str] = sorted(present_day_names, key=lambda x: day_order.index(x))
    pto_dates: List[datetime] = get_pto_dates(pto_calendar, pto_name, date_range)
    pto_count: int = len(pto_dates)
    updated_required_days: int = max(0, required_days - pto_count)
    present_count: int = min(updated_required_days, len(present_days))
    status_ok: bool = not (present_count < updated_required_days)
    absent_days: List[str] = [item for item in ['Tue', 'Wed', 'Thu'] if item not in present_day_names]
    if status_ok:
        absent_days = []

    return {
        'NAME': name,
        'DEPT': dept,
        'OFFICE': office,
        'STATUS': "O" if status_ok else "X",
        'SIGNIN_DAYS': '/'.join(present_day_names) if present_day_names else 'NO SIGNIN',
        'ABSENT_DAYS': '/'.join(absent_days) if absent_days else 'N/A',
        'SIGNIN_DETAILS': f"{present_count} / {updated_required_days} [ PTOs={pto_count} ]",
        'PTO_DAYS': ', '.join(sorted([date.strftime('%a') for date in pto_dates])) if pto_dates else 'N/A',
        'USED_PTOs': len(pto_dates),
        'PRESENT': sorted(present_dates),
        'REQUIRED': required_days,
    }

def process_signin(signin_df: DataFrame, date_range: DatetimeIndex, employees_df: DataFrame, pto_calendar: List[PTOData]) -> List[SignInData]:
    signin_summary: List[SignInData] = [process_employee_signin(row, signin_df, date_range, pto_calendar) for _, row in employees_df.iterrows()]
    signin_summary = [row for row in signin_summary if row['REQUIRED'] != 0]
    return signin_summary

### Display Functions ###
def highlight_row(row: Dict[str, str]) -> List[str]:
    signin_details: List[str] = row['SIGNIN_DETAILS'].split(' ')
    present_days: int = int(signin_details[0])
    required_days: int = int(signin_details[2])
    return [f"background-color: {STATUS_X_BG_COLOR};" if present_days < required_days else ''] * len(row)

def create_styled_dataframe(signin_summary: List[SignInData]) -> Styler:
    df: DataFrame = DataFrame(signin_summary)
    df = df.sort_values(by=['OFFICE', 'DEPT', 'NAME'])
    return df.style.apply(highlight_row, axis=1)

def display_signin_summary(signin_summary: List[SignInData], start_date: datetime, end_date: datetime) -> None:
    signin_summary_df: DataFrame = DataFrame(signin_summary)
    st.subheader("Weekly Signin Data")
    st.write(f"[ Week of {start_date.strftime('%m/%d/%Y')} - {end_date.strftime('%m/%d/%Y')} ]")

    dynamic_filters: DynamicFilters = DynamicFilters(signin_summary_df, filters=['STATUS', 'OFFICE', 'SIGNIN_DAYS', 'USED_PTOs'])
    with st.sidebar:
        st.subheader("Apply filter(s) you want to 👇")
    dynamic_filters.display_filters(location='sidebar')
    filtered_df = dynamic_filters.filter_df()

    styled_signin_table = create_styled_dataframe(filtered_df.to_dict('records'))
    st.dataframe(styled_signin_table, hide_index=True)
    st.html(f"<code class='num-of-rows'>Number of rows: {len(filtered_df)}</code>")

### Main Function ###
def main() -> None:
    if not check_password():
        st.stop()

    st.title("Madwell Signin App")
    load_css("style.css")

    employees_df, pto_calendar = load_data()
    uploaded_files: List[Any] = st.file_uploader("Choose CSV file(s) of weekly signin data. [ Sunday to Saturday ]", accept_multiple_files=True, type="csv")

    if uploaded_files:
        signin_df, start_date, end_date = process_uploaded_files(uploaded_files)
        if not signin_df.empty:
            date_range: DatetimeIndex = pd.date_range(start=start_date, end=end_date)
            signin_summary: List[SignInData] = process_signin(signin_df, date_range, employees_df, pto_calendar)
            display_signin_summary(signin_summary, start_date, end_date)
    else:
        st.warning("Please upload the CSV file(s) to proceed.")

if __name__ == "__main__":
    main()
