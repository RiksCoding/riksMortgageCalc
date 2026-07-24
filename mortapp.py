import datetime
import calendar
import streamlit as st
import pandas as pd
import math

DEBUG_MODE=False
DD_INIITAL_WAIT = 14
#=================================================
# Mortgage Logic
#=================================================

class Mortgage:
    def __init__(self, principal, annual_rate, term_years, term_months, start_date, payment_day, cap_day, is_int_only = False, cap_in_stub_month=False):
        self.principal = principal
        self.annual_rate = annual_rate
        self.term_years = term_years
        self.actual_term_months = term_years * 12 + term_months
        self.is_int_only = is_int_only
        self.start_date = start_date
        self.payment_day = payment_day
        self.cap_day = cap_day
        self.cap_in_stub_month = cap_in_stub_month

        self.end_date = self._calculate_end_date()
        self.first_payment_date = self._get_first_payment_date()

        last_day_start_month = calendar.monthrange(self.start_date.year, self.start_date.month)[1]
        self.end_of_start_month = datetime.date(self.start_date.year, self.start_date.month, last_day_start_month)

    def _calculate_end_date(self):
        """ Calculate the end date of the mortgage based on the start date and term. Checks if the end date
        falls on a valid day of the month, or returns last day of the month"""
        total_months = self.start_date.month - 1 + self.actual_term_months
        end_year = self.start_date.year + total_months // 12
        end_month = total_months % 12 + 1

        end_day = min(self.start_date.day, calendar.monthrange(end_year, end_month)[1])
        return datetime.date(end_year, end_month, end_day)

    def _get_effective_day(self, date, target_day):
        """Calculate the payday for a given date, for 'last' returns the last day, and
        accounts for months with fewer days than the target day."""
        last_day_of_month = calendar.monthrange(date.year, date.month)[1]
        if target_day == 'last':
            return last_day_of_month
        return min(int(target_day), last_day_of_month)
        
    def _get_first_payment_date(self):
        """Ensure that 14 days pass between start date and first payment date
        otherwise defer the first payment to the next month."""
        #Can't pay for at least 14 days
        min_dd_date = self.start_date + datetime.timedelta(days=DD_INIITAL_WAIT)
        # Can you pay today?
        proposed_first_payment_date = self.start_date
        while True:
            #is the proposed first pay day the same as the actual pay day?
            if proposed_first_payment_date.day == self._get_effective_day(proposed_first_payment_date, self.payment_day):
                #is it after the min DD date?
                if proposed_first_payment_date >= min_dd_date:
                    return proposed_first_payment_date
            proposed_first_payment_date += datetime.timedelta(days=1)
        
    def simulate_mortgage(self, monthly_payment, generate_statement=False):
        current_date = self.start_date
        balance = self.principal
        accrued_interest = 0.0
        stub_interest_accrued = 0.0
        payments_made = 0
        statement = []

        def log_transaction(event, amount):
            if generate_statement:
                statement.append({
                    "Date": current_date,
                    "Event": event,
                    "Amount": amount,
                    "Closing Balance": balance
                })

        log_transaction("Initial Advance", self.principal)

        # Speed up by only working out effective dates once a month
        current_month = -1
        effective_pay_day = -1
        effective_cap_day = -1
        days_in_year = 365

        # State Machine for mortgage simulation
        while current_date <= self.end_date:

            if current_date.month != current_month:
                current_month = current_date.month
                days_in_month = calendar.monthrange(current_date.year, current_month )[1]
                effective_pay_day = self._get_effective_day(current_date, self.payment_day)
                effective_cap_day = self._get_effective_day(current_date, self.cap_day)
                days_in_year = 366 if calendar.isleap(current_date.year) else 365

            # Payments First...
            if current_date.day == effective_pay_day and current_date >= self.first_payment_date:
                if payments_made < 1:
                    if self.cap_in_stub_month:
                        #interest is capitalised, payments are normal
                        target_payment = monthly_payment
                    else:
                        #Sweep broken interest into first payment
                        target_payment = monthly_payment + stub_interest_accrued
                        if generate_statement and stub_interest_accrued > 0:
                            log_transaction("(Broken Interest Added to 1st Payment: £" + str(math.ceil(stub_interest_accrued*100)/100)+")",0)
                else:
                    target_payment = monthly_payment

                payment_to_apply = max(0, min(target_payment, balance + accrued_interest))

                if payment_to_apply > 0:
                    balance -= payment_to_apply

                    if payments_made  > 0:
                        log_transaction("Monthly Payment", -payment_to_apply) 
                    else:
                        log_transaction("First Payment", -payment_to_apply)

                    payments_made += 1

            # Then Capitalisation of Interest
            if current_date.day == effective_cap_day and accrued_interest > 0:
                in_start_month = (current_date.year == self.start_date.year and current_date.month == self.start_date.month)    
                if not in_start_month or self.cap_in_stub_month:
                    capitalised_amount = accrued_interest
                    balance += capitalised_amount
                    accrued_interest = 0.0 #So statement shows no accrued interest 

                    log_transaction("Capitalisation", capitalised_amount)

            #Then Accrue Interest on Closing Balance
            daily_interest = balance * (self.annual_rate / days_in_year)
            accrued_interest += daily_interest

            #accumulate stub interest on inital month
            if current_date <= self.end_of_start_month:
                stub_interest_accrued += daily_interest
            if current_date == self.end_date:
                if accrued_interest > 0:
                            balance += accrued_interest
                            log_transaction("Final Interest Accrual", accrued_interest)
                            accrued_interest = 0.0
            
            #advance to next day
            current_date += datetime.timedelta(days=1)

            
        return balance if not generate_statement else statement

    def calculate_monthly_payment(self):
        """Itteratively calculate the monthly payment to account for being
        able to capitalise and pay on arbitrary days of the month."""
        if self.is_int_only:
            monthly_payment = self.principal * (self.annual_rate / 12)
            return math.ceil(monthly_payment * 100) / 100

        r = self.annual_rate / 12
        n = self.actual_term_months
        if n > 0:
            if r > 0:
                standard_pmt = self.principal * r / (1-(1+r)**(-n))
            else:
                standard_pmt = self.principal /n 
            low = standard_pmt * 0.5
            high = standard_pmt * 2.0
        else:
            high = self.principal
            low = 0.01
        while (high - low) > 0.001:
            mid = (low + high) / 2.0
            final_balance = self.simulate_mortgage(mid)

            if final_balance > 0:
                low = mid
            else:
                high = mid

        return math.ceil (mid * 100) / 100  # Round up to nearest penny

def DEBUG_PRINT(value, var_name=None):
    if DEBUG_MODE:
        if var_name is None:
            print(f"[DEBUG] {value}")
        else:
            print(f"[DEBUG] {var_name} = {value}")

#=================================================
# User Interface (Streamlit)
#=================================================
st.set_page_config(page_title="Rik's Mortgage Simulator", page_icon='🏠',layout="wide")
st.title("Rik's Mortgage Simulator")
st.markdown("Calculates the monthly payment and simulates the mortgage allowing for payment and capitalisation to occur on arbitary days")

# Inputs
st.sidebar.header("Mortgage Parameters")

principal = st.sidebar.number_input("Principal (£)", min_value=0, value=250000, step=1000)
annual_interest_rate = st.sidebar.number_input("Annual Interest Rate (%)", min_value = 0.0, max_value = 20.0, value = 4.5, step = 0.01)

col1, col2 = st.sidebar.columns(2)
with col1:
    term_years = st.number_input("Term (Years)", min_value=0, value=25, step=1, max_value = 40)
with col2:
    term_months = st.number_input("Term (Months)", min_value=0, value=0, step=1, max_value = 11)

is_int_only = st.sidebar.checkbox("Pay Interest Only", False)

start_date = st.sidebar.date_input("Start Date", value=datetime.date.today())   

day_options = ['last']+[str(i) for i in range(1,29)]
payment_day = st.sidebar.selectbox("Payment Day", options=day_options, index=1) # default to 1st
cap_day = st.sidebar.selectbox("Capitalisation Day", options=day_options, index=0) # default to last day
cap_in_stub_month = st.sidebar.checkbox("Capitalise Interest in First (Broken) Month", False)
# Call Events Engine
with st.spinner("Calculating..."):
    mortgage = Mortgage(
        principal=principal,
        annual_rate=annual_interest_rate / 100,
        term_years=term_years,
        term_months=term_months,
        start_date=start_date,
        payment_day=payment_day,
        cap_day=cap_day,
        is_int_only=is_int_only,
        cap_in_stub_month=cap_in_stub_month
    )

    exact_payment = mortgage.calculate_monthly_payment()

    statement = mortgage.simulate_mortgage(exact_payment, generate_statement=True)
    df = pd.DataFrame(statement)

    # Display Output in main window
    st.metric(label="Required Monthly Payment ", value=f"£{exact_payment:,.2f}")

    

    st.divider()

    def format_currency(val):
        if pd.isna(val):
            return ""
        if val < 0 : 
            return f"-£{abs(val):,.2f}"
        else:
            return f"£{val:,.2f}"

    df_display = df.copy()
    df_display['Date'] = df_display['Date'].apply(lambda x : x.strftime("%d/%m/%Y"))
    df_display['Amount'] = df_display['Amount'].apply(format_currency)
    df_display['Closing Balance'] = df_display['Closing Balance'].apply(format_currency)

    st.subheader("Mortgage Statement")
    st.dataframe(df_display, width="stretch", hide_index=True, 
                 column_config={
                        "Date": st.column_config.TextColumn("Date", width="medium"),
                        "Event": st.column_config.TextColumn("Event", width="large"),
                        "Amount": st.column_config.TextColumn("Amount", alignment="right"),          # Right-aligned
                        "Closing Balance": st.column_config.TextColumn("Closing Balance", alignment="right") # Right-aligned
                })

    st.divider()
    
    st.subheader("Mortgage Balance over Time")
    chart_data = df[df['Event'].isin(['Initial Advance', 'Monthly Payment', 'First Payment'])][['Date', 'Closing Balance']].copy()
    chart_data.set_index('Date', inplace=True)
    st.line_chart(chart_data)