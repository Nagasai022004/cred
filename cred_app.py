import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import base64
import os
from fpdf import FPDF

# ---------- Google Sheets Setup ----------
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = ServiceAccountCredentials.from_json_keyfile_name("google_credentials.json", scope)
client = gspread.authorize(credentials)
sheet = client.open("UserTransactions")

# Worksheets
users_sheet = sheet.worksheet("Users")
transactions_sheet = sheet.worksheet("Transactions")

# ---------- Helper Functions ----------
def get_all_users():
    return users_sheet.get_all_records()

def add_transaction(user_email, amount, type_, description):
    if type_ == 'credit':
        return  # Ignore credit transactions
    timestamp = datetime.now().isoformat()
    transactions_sheet.append_row([user_email, amount, type_, description, timestamp])

def get_user_transactions(user_email):
    all_transactions = transactions_sheet.get_all_records()
    return [t for t in all_transactions if t['UserEmail'] == user_email]

def delete_transaction(user_email, timestamp):
    all_data = transactions_sheet.get_all_records()
    for idx, row in enumerate(all_data, start=2):
        if row['UserEmail'] == user_email and row['Timestamp'] == timestamp:
            transactions_sheet.delete_rows(idx)
            break

def delete_transactions_between_dates(start_date, end_date):
    all_data = transactions_sheet.get_all_records()
    for idx in reversed(range(len(all_data))):
        ts = datetime.fromisoformat(all_data[idx]['Timestamp'])
        if start_date <= ts <= end_date:
            transactions_sheet.delete_rows(idx + 2)

def calculate_user_dues():
    user_dues = {}
    transactions = transactions_sheet.get_all_records()
    for t in transactions:
        email = t['UserEmail']
        amount = float(t['Amount'])
        if t['Type'] == 'debit':
            user_dues[email] = user_dues.get(email, 0) + amount
    return user_dues

def export_pdf(user_email):
    transactions = get_user_transactions(user_email)
    user = next(u for u in get_all_users() if u['Email'] == user_email)

    today = datetime.today()
    if today.day >= 13:
        bill_start = today.replace(day=13)
    else:
        bill_start = (today.replace(day=1) - timedelta(days=1)).replace(day=13)
    bill_end = bill_start + timedelta(days=30)
    due_date = bill_start + timedelta(days=50)

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Statement for {user['Name']} ({user['Email']})", ln=True)
    pdf.cell(200, 10, txt=f"Billing Period: {bill_start.date()} to {bill_end.date()}", ln=True)
    pdf.cell(200, 10, txt=f"Due Date: {due_date.date()}", ln=True)
    pdf.ln(10)

    pdf.set_font("Arial", 'B', 12)
    pdf.cell(50, 10, "Date", 1)
    pdf.cell(30, 10, "Type", 1)
    pdf.cell(40, 10, "Amount", 1)
    pdf.cell(70, 10, "Description", 1)
    pdf.ln()

    pdf.set_font("Arial", size=12)
    total_due = 0
    for t in transactions:
        t_date = t['Timestamp'][:19]
        if bill_start.isoformat() <= t['Timestamp'] <= bill_end.isoformat():
            if t['Type'] == 'debit':
                total_due += float(t['Amount'])
            pdf.cell(50, 10, t_date, 1)
            pdf.cell(30, 10, t['Type'].upper(), 1)
            pdf.cell(40, 10, f"Rs.{float(t['Amount']):.2f}", 1)
            desc = (t['Description'][:30] + '...') if len(t['Description']) > 33 else t['Description']
            pdf.cell(70, 10, desc, 1)
            pdf.ln()

    pdf.ln(5)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, txt=f"TOTAL DUE: Rs.{total_due:.2f}", ln=True)

    filename = f"{user['Name'].replace(' ', '_')}_due_{due_date.date()}.pdf"
    pdf.output(filename)

    with open(filename, "rb") as f:
        base64_pdf = base64.b64encode(f.read()).decode('utf-8')
        pdf_display = f'<a href="data:application/octet-stream;base64,{base64_pdf}" download="{filename}">Download PDF Statement</a>'
        st.markdown(pdf_display, unsafe_allow_html=True)

    os.remove(filename)

# ---------- Streamlit UI ----------
st.set_page_config(page_title="Transaction Manager", layout="centered")
st.title("📊 Google Sheets Transaction Manager")

all_users = get_all_users()
names = [u['Name'] for u in all_users]
selected = st.selectbox("Select User", names)
selected_user = next(u for u in all_users if u['Name'] == selected)

# Tabs
tabs = st.tabs(["➕ Add Transaction", "📄 View Transactions", "📤 Export PDF", "📊 All User Dues", "🧹 Delete Between Dates"])

with tabs[0]:
    amount = st.number_input("Amount")
    type_ = 'debit'
    description = st.text_input("Description")
    if st.button("Add Transaction"):
        add_transaction(selected_user['Email'], amount, type_, description)
        st.success("Transaction Added")

with tabs[1]:
    st.dataframe(get_user_transactions(selected_user['Email']))

with tabs[2]:
    export_pdf(selected_user['Email'])

with tabs[3]:
    st.subheader("All Users Dues")
    dues = calculate_user_dues()
    users = get_all_users()
    total_due = 0
    data = []
    for u in users:
        email = u['Email']
        due = dues.get(email, 0)
        total_due += due
        data.append({"Name": u['Name'], "Email": email, "Due (Rs)": round(due, 2)})
    st.dataframe(data)
    st.write(f"### Total Due: Rs.{total_due:.2f}")

with tabs[4]:
    st.subheader("Delete Transactions Between Two Dates")
    start = st.date_input("Start Date")
    end = st.date_input("End Date")
    if st.button("Delete Transactions"):
        delete_transactions_between_dates(datetime.combine(start, datetime.min.time()), datetime.combine(end, datetime.max.time()))
        st.success("Transactions deleted.")
