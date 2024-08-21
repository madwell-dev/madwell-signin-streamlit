"""
signin.py

This module handles the signin summary data processing and visualization.
It includes functions to filter data, display filtered data, and draw charts
using Streamlit and Altair.
"""

import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, TypedDict, Tuple

import hmac
import altair as alt
import pandas as pd
from pandas import DataFrame, DatetimeIndex
from pandas.io.formats.style import Styler
import requests
import streamlit as st

### Constants ###
USER_AGENT: str = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/91.0.4472.114 Safari/537.36"
)
HEADERS: Dict[str, str] = {"User-Agent": USER_AGENT}
DATE_FORMAT: str = "%m/%d/%Y %I:%M %p"
STATUS_X_BG_COLOR = "rgba(251, 231, 239, 0.5)"


### Type Definitions ###
class LeaveHourDetail(TypedDict):
    """
    A TypedDict representing the details of leave hours for a specific date.

    Attributes:
        date (str): The date of the leave.
        dailyHours (str): The number of leave hours for the date.
    """

    date: str
    dailyHours: str


class PTOData(TypedDict):
    """
    A TypedDict representing the data for Paid Time Off (PTO).

    Attributes:
        employeeId (str): The ID of the employee.
        name (str): The name of the employee.
        leaveType (str): The type of leave.
        leaveTypeDescription (str): The description of the leave type.
        status (str): The status of the leave request.
        leaveRequest (str): The leave request details.
        checksum (str): The checksum for the leave request.
        startDate (str): The start date of the leave.
        endDate (str): The end date of the leave.
        comments (str): Any comments related to the leave.
        leaveDates (List[str]): The dates of the leave.
        vouchers (List): The vouchers associated with the leave.
        leaveHours (int): The total leave hours.
        leaveHourDetails (List[LeaveHourDetail]): The details of leave hours.
        absenceCodeReason (str): The reason code for the absence.
        ptoRegisterTypeCode (str): The register type code for the PTO.
    """

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
    vouchers: List[any]
    leaveHours: int
    leaveHourDetails: List[LeaveHourDetail]
    absenceCodeReason: str
    ptoRegisterTypeCode: str


class SignInData(TypedDict):
    """
    A TypedDict representing the sign-in data for an employee.

    Attributes:
        NAME (str): The name of the employee.
        DEPT (str): The department of the employee.
        OFFICE (str): The office location of the employee.
        STATUS (str): The sign-in status of the employee.
        SIGNIN_DAYS (str): The number of sign-in days.
        ABSENT_DAYS (str): The number of absent days.
        SIGNIN_DETAILS (str): The details of the sign-in.
        PTO_DAYS (str): The number of PTO days.
        USED_PTOs (int): The number of used PTOs.
        PRESENT (List[datetime]): The dates the employee was present.
        REQUIRED (int): The number of required sign-in days.
    """

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
    """
    Handles the password input and checks if it matches the stored secret password.
    Updates the session state based on the comparison result.
    """
    if hmac.compare_digest(st.session_state["password"], st.secrets["password"]):
        st.session_state["password_correct"] = True
        del st.session_state["password"]
    else:
        st.session_state["password_correct"] = False
        st.session_state["password"] = ""


def check_password() -> bool:
    """
    Prompts the user to enter a password and checks if it is correct.
    Returns True if the password is correct, otherwise False.

    Returns:
        bool: True if the password is correct, False otherwise.
    """
    if st.session_state.get("password_correct", False):
        return True
    st.text_input(
        "Password", type="password", on_change=password_entered, key="password"
    )
    if "password_correct" in st.session_state:
        st.error("😕 Password incorrect")
    return False


### Styling Function ###
def load_css(filename: str) -> None:
    """
    Loads a CSS file and applies the styles to the Streamlit app.

    Args:
        filename (str): The path to the CSS file.
    """
    with open(filename, encoding="utf-8") as file:
        css = file.read()
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


### Data Fetching Functions ###
@st.cache_data(ttl=600)
def fetch_pto_data(pto_url: str, username: str, password: str) -> List[PTOData]:
    """
    Fetches PTO data from the given URL using the provided username and password.

    Args:
        pto_url (str): The URL to fetch PTO data from.
        username (str): The username for authentication.
        password (str): The password for authentication.

    Returns:
        List[PTOData]: A list of PTO data dictionaries. Returns an empty list if an error occurs.
    """
    try:
        response: requests.Response = requests.get(
            pto_url, auth=(username, password), headers=HEADERS, timeout=10
        )
        response.raise_for_status()
        pto_calendar_json: str = response.text
        return json.loads(pto_calendar_json)["requestList"]
    except (
        requests.exceptions.HTTPError,
        requests.exceptions.RequestException,
        json.JSONDecodeError,
    ) as err:
        st.error(f"Error occurred while fetching PTO data: {err}")
        return []


@st.cache_data(ttl=600)
def load_data() -> Tuple[DataFrame, List[PTOData]]:
    """
    Loads employee data and PTO data.

    The function fetches employee data from a CSV file specified by the URL in the
    Streamlit secrets. It also fetches PTO data using the provided URL, username,
    and password from the Streamlit secrets.

    Returns:
        Tuple[DataFrame, List[PTOData]]: A tuple containing the employee DataFrame
        and a list of PTO data dictionaries.
    """
    employees_df: DataFrame = pd.read_csv(st.secrets["roaster_url"])
    pto_calendar: List[PTOData] = fetch_pto_data(
        st.secrets["pto_url"], st.secrets["username"], st.secrets["password"]
    )
    return employees_df, pto_calendar


### Signin CSV Processing Functions ###
@st.cache_data(ttl=600)
def combine_csv_files(uploaded_files: List[bytes]) -> DataFrame:
    """
    Combines multiple CSV files into a single DataFrame.

    Args:
        uploaded_files (List[bytes]): A list of uploaded CSV files in bytes format.

    Returns:
        DataFrame: A combined DataFrame containing data from all uploaded CSV files.
    """
    combined_df: DataFrame = DataFrame()
    for i, uploaded_file in enumerate(uploaded_files):
        df: DataFrame = pd.read_csv(
            uploaded_file, skiprows=1 if i > 0 else 0, header=None if i > 0 else "infer"
        )
        if i > 0:
            df.columns = combined_df.columns
        combined_df = pd.concat([combined_df, df], ignore_index=True)
    return combined_df


@st.cache_data(ttl=600)
def calculate_date_range(
    combined_df: DataFrame,
) -> Tuple[datetime, datetime, bool, datetime, datetime]:
    """
    Calculates the date range from the combined DataFrame.

    Args:
        combined_df (DataFrame): The combined DataFrame containing sign-in data.

    Returns:
        Tuple[datetime, datetime, bool, datetime, datetime]: A tuple containing:
            - start_date (datetime): The start date of the date range.
            - end_date (datetime): The end date of the date range.
            - more_than_7_days (bool): Whether the date range spans more than 7 days.
            - min_date (datetime): The minimum date in the DataFrame.
            - max_date (datetime): The maximum date in the DataFrame.
    """
    combined_df["In time"] = pd.to_datetime(
        combined_df["In time"], format=DATE_FORMAT)
    min_date: datetime = combined_df["In time"].min()
    max_date: datetime = combined_df["In time"].max()
    more_than_7_days: bool = (max_date - min_date).days > 7
    start_date: datetime = (min_date - timedelta(days=min_date.weekday() + 1)).replace(
        hour=1, minute=0, second=0, microsecond=0
    )
    if min_date.weekday() == 6:
        start_date += timedelta(days=7)
    end_date: datetime = start_date + timedelta(days=6)
    return start_date, end_date, more_than_7_days, min_date, max_date


@st.cache_data(ttl=600)
def load_signin_data(
    uploaded_files: List[bytes],
) -> Tuple[DataFrame, datetime, datetime]:
    """
    Loads and processes sign-in data from uploaded CSV files.

    This function combines multiple uploaded CSV files into a single DataFrame,
    calculates the date range, and checks if the data covers more than 7 days.
    If the data covers more than 7 days, a warning is displayed and the process
    is stopped.

    Args:
        uploaded_files (List[bytes]): A list of uploaded CSV files in bytes format.

    Returns:
        Tuple[DataFrame, datetime, datetime]: A tuple containing the combined DataFrame,
        the start date, and the end date of the date range.
    """
    combined_df: DataFrame = combine_csv_files(uploaded_files)
    start_date, end_date, more_than_7_days, min_date, max_date = calculate_date_range(
        combined_df
    )
    if more_than_7_days:
        st.warning(
            f"Your data covers more than 7 days ({min_date.strftime('%m/%d/%Y')} - "
            f"{max_date.strftime('%m/%d/%Y')}). Please upload only 7 days of data [Sun-Sat]."
        )
        st.stop()
    else:
        st.success(f"Successfully uploaded {len(combined_df)} lines of data.")
    return combined_df, start_date, end_date


@st.cache_data(ttl=600)
def process_uploaded_files(
    uploaded_files: List[Any],
) -> Tuple[DataFrame, datetime, datetime]:
    """
    Processes uploaded files to extract sign-in data.

    This function loads and processes sign-in data from the uploaded files by
    calling the load_signin_data function.

    Args:
        uploaded_files (List[Any]): A list of uploaded files.

    Returns:
        Tuple[DataFrame, datetime, datetime]: A tuple containing the sign-in DataFrame,
        the start date, and the end date of the date range.
    """
    signin_df, start_date, end_date = load_signin_data(uploaded_files)
    return signin_df, start_date, end_date


### Singin Data Processing Functions ###
def get_pto_dates(
    pto_calendar: List[PTOData], pto_name: str, date_range: DatetimeIndex
) -> List[datetime]:
    """
    Retrieves PTO dates for a specific employee within a given date range.

    This function iterates through the PTO calendar to find leave dates for the specified
    employee (pto_name) and checks if those dates fall within the given date range and
    are on a Tuesday, Wednesday, or Thursday.

    Args:
        pto_calendar (List[PTOData]): A list of PTO data dictionaries.
        pto_name (str): The name of the employee to retrieve PTO dates for.
        date_range (DatetimeIndex): The range of dates to check for PTO.

    Returns:
        List[datetime]: A list of datetime objects representing the PTO dates for the
        specified employee within the given date range.
    """
    pto_dates: List[datetime] = []
    for pto in pto_calendar:
        if pto["name"] == pto_name:
            for leave_date in pto["leaveDates"]:
                leave_date: datetime = datetime.strptime(
                    leave_date, "%Y-%m-%d"
                ).replace(hour=1, minute=0, second=0, microsecond=0)
                if leave_date.weekday() in [1, 2, 3] and leave_date in date_range:
                    pto_dates.append(leave_date)
    return pto_dates


def process_employee_signin(
    row: Dict[str, str],
    signin_df: DataFrame,
    date_range: DatetimeIndex,
    pto_calendar: List[PTOData],
) -> SignInData:
    """
    Processes the sign-in data for an employee.

    This function processes the sign-in data for a specific employee, calculates the
    number of present days, PTO days, and determines the employee's attendance status.

    Args:
        row (Dict[str, str]): A dictionary containing employee information.
        signin_df (DataFrame): A DataFrame containing sign-in data.
        date_range (DatetimeIndex): The range of dates to check for sign-ins.
        pto_calendar (List[PTOData]): A list of PTO data dictionaries.

    Returns:
        SignInData: A dictionary containing processed sign-in data for the employee.
    """
    name: str = row["FULL_NAME"]
    pto_name: str = row["JW_NAME"]
    dept: str = row["DEPARTMENT"]
    office: str = row["OFFICE"]
    required_days: int = int(row["REQUIRED_DAYS"])

    day_order: List[str] = ["Tue", "Wed", "Thu"]
    present_days: DataFrame = signin_df[signin_df["Name"] == name]
    present_days = present_days[
        present_days["In time"].dt.strftime("%a").isin(["Tue", "Wed", "Thu"])
    ]
    present_dates: List[datetime] = list(
        set(present_days["In time"].dt.strftime("%m/%d/%Y").tolist())
    )
    present_day_names: List[str] = set(
        present_days["In time"].dt.strftime("%a"))
    present_day_names: List[str] = sorted(
        present_day_names, key=day_order.index)
    pto_dates: List[datetime] = get_pto_dates(
        pto_calendar, pto_name, date_range)
    pto_dates: List[datetime] = sorted(
        pto_dates, key=lambda date: day_order.index(date.strftime("%a"))
    )
    pto_count: int = len(pto_dates)
    updated_required_days: int = max(0, required_days - pto_count)
    present_count: int = min(updated_required_days, len(present_days))
    status_ok: bool = not (present_count < updated_required_days)
    absent_days: List[str] = [
        item for item in ["Tue", "Wed", "Thu"] if item not in present_day_names
    ]
    if status_ok:
        absent_days = []

    return {
        "NAME": name,
        "DEPT": dept,
        "OFFICE": office,
        "STATUS": "O" if status_ok else "X",
        "SIGNIN_DAYS": (
            "/".join(present_day_names) if present_day_names else "NO SIGNIN"
        ),
        "ABSENT_DAYS": "/".join(absent_days) if absent_days else "N/A",
        "SIGNIN_DETAILS": f"{present_count} / {updated_required_days} [ PTOs={pto_count} ]",
        "PTO_DAYS": (
            ", ".join([date.strftime("%a") for date in pto_dates])
            if pto_dates
            else "N/A"
        ),
        "USED_PTOs": len(pto_dates),
        "PRESENT": sorted(present_dates),
        "REQUIRED": required_days,
    }


def process_signin(
    signin_df: DataFrame,
    date_range: DatetimeIndex,
    employees_df: DataFrame,
    pto_calendar: List[PTOData],
) -> List[SignInData]:
    """
    Processes the sign-in data for all employees.

    This function iterates through the employee DataFrame, processes the sign-in data
    for each employee, and filters out employees with no required sign-in days.

    Args:
        signin_df (DataFrame): A DataFrame containing sign-in data.
        date_range (DatetimeIndex): The range of dates to check for sign-ins.
        employees_df (DataFrame): A DataFrame containing employee information.
        pto_calendar (List[PTOData]): A list of PTO data dictionaries.

    Returns:
        List[SignInData]: A list of dictionaries containing processed sign-in data
        for each employee.
    """
    signin_summary: List[SignInData] = [
        process_employee_signin(row, signin_df, date_range, pto_calendar)
        for _, row in employees_df.iterrows()
    ]
    signin_summary = [row for row in signin_summary if row["REQUIRED"] != 0]
    return signin_summary


### Display Functions ###
def highlight_row(row: Dict[str, str]) -> List[str]:
    """
    Highlights a row based on the sign-in details.

    This function takes a row of sign-in data, extracts the number of present days
    and required days, and returns a list of styles to apply to the row. If the number
    of present days is less than the required days, the row is highlighted with a
    background color.

    Args:
        row (Dict[str, str]): A dictionary containing sign-in data for an employee.

    Returns:
        List[str]: A list of styles to apply to the row.
    """
    signin_details: List[str] = row["SIGNIN_DETAILS"].split(" ")
    present_days: int = int(signin_details[0])
    required_days: int = int(signin_details[2])
    return [
        (
            f"background-color: {STATUS_X_BG_COLOR};"
            if present_days < required_days
            else ""
        )
    ] * len(row)


def create_styled_dataframe(signin_summary: List[SignInData]) -> Styler:
    """
    Creates a styled DataFrame for the sign-in summary.

    This function takes a list of sign-in data, converts it to a DataFrame,
    sorts it by department, office, and name, and applies a custom styling
    function to highlight rows.

    Args:
        signin_summary (List[SignInData]): A list of dictionaries containing
        sign-in data for each employee.

    Returns:
        Styler: A pandas Styler object with the applied styles.
    """
    df: DataFrame = DataFrame(signin_summary)
    df = df.sort_values(by=["DEPT", "OFFICE", "NAME"])
    return df.style.apply(highlight_row, axis=1)


@st.cache_data(ttl=600)
def convert_to_dataframe(signin_summary: List["SignInData"]) -> DataFrame:
    """
    Converts the sign-in summary to a DataFrame.

    This function takes a list of sign-in data and converts it to a pandas
    DataFrame. The result is cached for 600 seconds to improve performance.

    Args:
        signin_summary (List[SignInData]): A list of dictionaries containing
        sign-in data for each employee.

    Returns:
        DataFrame: A pandas DataFrame containing the sign-in data.
    """
    return DataFrame(signin_summary)


def get_filters() -> dict:
    """
    Retrieves the filters selected by the user from the Streamlit sidebar.

    This function creates a sidebar in the Streamlit app where users can select
    various filters for the sign-in data. The selected options are stored in a
    dictionary and returned.

    Returns:
        dict: A dictionary containing the selected filter options.
    """
    with st.sidebar:
        st.subheader("Apply filter(s) you want to 👇")
        filters = {
            "STATUS": {
                "options": ["All", "O", "X"],
                "column": "STATUS",
            },
            "OFFICE": {
                "options": ["All", "Brooklyn, NY", "Denver, CO"],
                "column": "OFFICE",
            },
            "NO_SIGNIN": {
                "options": ["All", "NO SIGNIN"],
                "column": "SIGNIN_DAYS",
            },
            "USED_PTOs": {
                "options": ["All", "None used", "PTO used"],
                "column": "USED_PTOs",
                "custom_logic": {
                    "None used": lambda df: df[df["USED_PTOs"] == 0],
                    "PTO used": lambda df: df[df["USED_PTOs"].isin([1, 2, 3])],
                },
            },
        }
        for filter_name, filter_info in filters.items():
            selected_option = st.sidebar.selectbox(
                f"Filter by {filter_name}", options=filter_info["options"]
            )
            filters[filter_name]["selected_option"] = selected_option
    return filters


def apply_filters(df: DataFrame, filters: dict) -> DataFrame:
    """
    Applies the selected filters to the DataFrame.

    This function iterates through the provided filters and applies them to the
    DataFrame. If a custom logic is defined for a filter, it uses that logic;
    otherwise, it filters the DataFrame based on the selected option.

    Args:
        df (DataFrame): The DataFrame to be filtered.
        filters (dict): A dictionary containing filter information and selected options.

    Returns:
        DataFrame: The filtered DataFrame.
    """
    for _, filter_info in filters.items():
        selected_option = filter_info["selected_option"]
        if selected_option != "All":
            if (
                "custom_logic" in filter_info
                and selected_option in filter_info["custom_logic"]
            ):
                df = filter_info["custom_logic"][selected_option](df)
            else:
                df = df[df[filter_info["column"]] == selected_option]
    return df


@st.cache_data(ttl=600)
def display_filtered_data(filtered_df: DataFrame) -> None:
    """
    Displays the filtered sign-in data in a styled DataFrame.

    This function takes a filtered DataFrame, converts it to a styled DataFrame,
    and displays it using Streamlit. It also displays the number of rows in the
    filtered DataFrame.

    Args:
        filtered_df (DataFrame): The filtered DataFrame to be displayed.

    Returns:
        None
    """
    styled_signin_table: Styler = create_styled_dataframe(
        filtered_df.to_dict("records")
    )
    st.dataframe(styled_signin_table, hide_index=True)
    st.html(
        f"<code class='num-of-rows'>Number of rows: {len(filtered_df)}</code>")


def display_signin_summary(
    signin_summary: List["SignInData"], start_date: datetime, end_date: datetime
) -> None:
    """
    Displays the sign-in summary for a given date range.

    This function takes a list of sign-in data, converts it to a DataFrame,
    applies user-selected filters, and displays the filtered data using Streamlit.
    If no data matches the filters, it displays a warning message.

    Args:
        signin_summary (List[SignInData]): A list of dictionaries containing
        sign-in data for each employee.
        start_date (datetime): The start date of the date range.
        end_date (datetime): The end date of the date range.

    Returns:
        None
    """
    signin_summary_df: DataFrame = convert_to_dataframe(signin_summary)
    st.subheader("Weekly Signin Data")
    st.write(
        f"[ Week of {start_date.strftime('%m/%d/%Y')} - {end_date.strftime('%m/%d/%Y')} ]"
    )

    filters = get_filters()
    filtered_df = apply_filters(signin_summary_df, filters)
    if filtered_df.empty:
        st.dataframe(filtered_df)
        st.warning("No data matches the filters.")
    else:
        display_filtered_data(filtered_df)


def draw_chart(signin_summary: list) -> None:
    """
    Draws a bar chart of the number of employees and the number of 'X' status
    employees by department.

    This function takes a list of sign-in data, calculates the number of employees
    and the number of 'X' status employees for each department, and displays a bar chart
    using Altair and Streamlit.

    Args:
        signin_summary (list): A list of dictionaries containing sign-in data for each employee.

    Returns:
        None
    """
    departments = list(set(entry["DEPT"] for entry in signin_summary))
    num_of_employees_by_dept = [
        sum(1 for entry in signin_summary if entry["DEPT"] == department)
        for department in departments
    ]
    x_of_employees_by_dept = [
        sum(
            1
            for entry in signin_summary
            if entry["DEPT"] == department and entry["STATUS"] == "X"
        )
        for department in departments
    ]
    max_num_in_chart = max(num_of_employees_by_dept) + 1
    chart_data = DataFrame(
        {
            "Departments": departments,
            "Num of Employees": num_of_employees_by_dept,
            "X of Employees": x_of_employees_by_dept,
        }
    )
    chart_data_long = chart_data.melt(
        id_vars="Departments", var_name="Color_Key", value_name="Count"
    )
    combined_chart = (
        alt.Chart(chart_data_long)
        .mark_bar()
        .encode(
            x=alt.X("Departments:N", title="Departments"),
            y=alt.Y(
                "Count:Q", title="Count", scale=alt.Scale(domain=[0, max_num_in_chart])
            ),
            color=alt.Color(
                "Color_Key:N",
                scale=alt.Scale(range=["#ddffdd", "#ff3377"]),
                legend=alt.Legend(title="", orient="top-right"),
            ),
            xOffset="Color_Key:N",
        )
        .properties(
            width="container",
        )
    )
    st.altair_chart(combined_chart, use_container_width=True)


### Main Function ###
def main() -> None:
    """
    Main function for the Madwell Signin App.

    This function handles the authentication, loads necessary data, processes
    uploaded CSV files, and displays the signin summary and chart using Streamlit.

    Args:
        None

    Returns:
        None
    """
    if not check_password():
        st.stop()

    st.title("Madwell Signin App")
    load_css("style.css")

    employees_df, pto_calendar = load_data()
    uploaded_files: List[Any] = st.file_uploader(
        "Choose CSV file(s) of weekly signin data. [ Sunday to Saturday ]",
        accept_multiple_files=True,
        type="csv",
    )

    if uploaded_files:
        signin_df, start_date, end_date = process_uploaded_files(
            uploaded_files)
        if not signin_df.empty:
            date_range: DatetimeIndex = pd.date_range(
                start=start_date, end=end_date)
            signin_summary: List[SignInData] = process_signin(
                signin_df, date_range, employees_df, pto_calendar
            )
            display_signin_summary(signin_summary, start_date, end_date)
            draw_chart(signin_summary)
    else:
        st.warning("Please upload the CSV file(s) to proceed.")


if __name__ == "__main__":
    main()
