#!/usr/bin/env python3
"""Seed VaaniSeva Lakebase with synthetic Indian BFSI data.

Can run standalone (uses env vars) or from setup.sh.
Generates: 50 customers, ~80 loans, ~600 payments, 30 call queue, 40 KB docs.
"""

import os
import random
from datetime import datetime, timedelta

import psycopg
from psycopg.rows import dict_row

# --- Connection from env vars ---
HOST = os.environ["LAKEBASE_HOST"]
DB = os.environ.get("LAKEBASE_DB_NAME", "vaaniseva")
USER = os.environ["LAKEBASE_USER"]
TOKEN = os.environ["LAKEBASE_TOKEN"]

conn = psycopg.connect(
    f"host={HOST} port=5432 dbname={DB} user={USER} sslmode=require",
    password=TOKEN,
    autocommit=True,
    row_factory=dict_row,
)

print(f"Connected to {DB} @ {HOST}")

# --- Clear existing data ---
for table in [
    "payment_history", "call_queue", "quality_scores",
    "call_logs", "loan_accounts", "knowledge_base", "customer_profiles",
]:
    conn.execute(f"DELETE FROM {table}")
print("Cleared existing data")

# =============================================================================
# Customers
# =============================================================================
INDIAN_NAMES = [
    "Rajesh Kumar", "Priya Sharma", "Amit Patel", "Sunita Devi", "Vikram Singh",
    "Meena Gupta", "Suresh Reddy", "Anita Joshi", "Deepak Verma", "Kavita Nair",
    "Ramesh Yadav", "Pooja Iyer", "Arun Mishra", "Shalini Das", "Manoj Tiwari",
    "Rekha Pandey", "Rahul Saxena", "Geeta Bhat", "Ashok Pillai", "Nisha Menon",
    "Vikas Chauhan", "Renu Aggarwal", "Sandeep Jain", "Lata Deshmukh", "Prakash Naidu",
    "Swati Kulkarni", "Nitin Patil", "Asha Banerjee", "Kiran Hegde", "Usha Sinha",
    "Sachin Malhotra", "Divya Rao", "Manish Thakur", "Savita Kapoor", "Ajay Dubey",
    "Poonam Choudhury", "Sunil Rathore", "Anjali Mukherjee", "Yogesh Bhatt", "Kamla Devi",
    "Rakesh Goyal", "Seema Shukla", "Vinod Rawat", "Rani Varma", "Harish Chandra",
    "Manju Agarwal", "Sanjay Misra", "Padma Krishnan", "Naveen Prasad", "Bhavna Shah",
]

CITIES = [
    "Mumbai", "Delhi", "Bangalore", "Chennai", "Hyderabad", "Pune", "Kolkata",
    "Ahmedabad", "Jaipur", "Lucknow", "Chandigarh", "Bhopal", "Indore",
    "Coimbatore", "Nagpur", "Vadodara", "Kochi", "Visakhapatnam", "Patna", "Ranchi",
]

LANG_BY_CITY = {
    "Mumbai": "mr", "Delhi": "hi", "Bangalore": "kn", "Chennai": "ta",
    "Hyderabad": "te", "Pune": "mr", "Kolkata": "bn", "Ahmedabad": "gu",
    "Jaipur": "hi", "Lucknow": "hi", "Chandigarh": "pa", "Bhopal": "hi",
    "Indore": "hi", "Coimbatore": "ta", "Nagpur": "mr", "Vadodara": "gu",
    "Kochi": "ml", "Visakhapatnam": "te", "Patna": "hi", "Ranchi": "hi",
}

RISK_TIERS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

for name in INDIAN_NAMES:
    city = random.choice(CITIES)
    lang = LANG_BY_CITY.get(city, "hi")
    phone = f"+91{random.randint(70000, 99999)}{random.randint(10000, 99999)}"
    last4 = f"{random.randint(1000, 9999)}"
    risk = random.choice(RISK_TIERS)
    conn.execute(
        "INSERT INTO customer_profiles (name, phone, city, language_pref, account_last4, risk_tier) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (name, phone, city, lang, last4, risk),
    )

customers = conn.execute("SELECT * FROM customer_profiles ORDER BY id").fetchall()
print(f"Created {len(customers)} customers")

# =============================================================================
# Loans
# =============================================================================
LOAN_TYPES = ["Personal Loan", "Home Loan", "Car Loan", "Education Loan", "Business Loan", "Gold Loan"]

loan_count = 0
for cust in customers:
    n_loans = random.choices([1, 2, 3], weights=[0.5, 0.35, 0.15])[0]
    for _ in range(n_loans):
        loan_type = random.choice(LOAN_TYPES)
        principal = random.choice([50000, 100000, 200000, 500000, 1000000, 2000000, 5000000])
        emi = round(principal * random.uniform(0.015, 0.04), 2)
        days_overdue = random.choices(
            [0, random.randint(1, 15), random.randint(16, 45), random.randint(46, 90), random.randint(91, 180)],
            weights=[0.3, 0.25, 0.2, 0.15, 0.1],
        )[0]
        overdue = round(emi * max(1, days_overdue // 30), 2) if days_overdue > 0 else 0
        last_pay = (
            (datetime.now() - timedelta(days=days_overdue + random.randint(0, 30))).date()
            if days_overdue > 0
            else (datetime.now() - timedelta(days=random.randint(1, 28))).date()
        )
        conn.execute(
            "INSERT INTO loan_accounts (customer_id, loan_type, principal, emi_amount, "
            "overdue_amount, days_overdue, last_payment_date) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (cust["id"], loan_type, principal, emi, overdue, days_overdue, last_pay),
        )
        loan_count += 1

print(f"Created {loan_count} loans")

# =============================================================================
# Payment History
# =============================================================================
PAYMENT_MODES = ["UPI", "NACH", "NEFT", "Cash", "Cheque", "Online Portal", "Mobile App"]

loans = conn.execute(
    "SELECT id, emi_amount, last_payment_date, days_overdue FROM loan_accounts"
).fetchall()

pay_count = 0
for loan in loans:
    n_payments = random.randint(3, 15)
    base_date = loan["last_payment_date"] or (datetime.now() - timedelta(days=180)).date()
    for i in range(n_payments):
        pay_date = base_date - timedelta(days=30 * i + random.randint(-5, 5))
        amount = round(loan["emi_amount"] * random.uniform(0.8, 1.2), 2)
        mode = random.choice(PAYMENT_MODES)
        status = random.choices(["SUCCESS", "FAILED", "BOUNCED"], weights=[0.9, 0.05, 0.05])[0]
        ref_id = f"PAY{random.randint(100000, 999999)}"
        conn.execute(
            "INSERT INTO payment_history (loan_id, payment_date, amount, payment_mode, status, reference_id) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (loan["id"], pay_date, amount, mode, status, ref_id),
        )
        pay_count += 1

print(f"Created {pay_count} payment records")

# =============================================================================
# Call Queue
# =============================================================================
overdue = conn.execute(
    "SELECT DISTINCT customer_id FROM loan_accounts WHERE days_overdue > 0"
).fetchall()

cq_count = 0
for oc in overdue[:30]:
    conn.execute(
        "INSERT INTO call_queue (customer_id, priority, scheduled_at, status) "
        "VALUES (%s, %s, %s, 'PENDING')",
        (oc["customer_id"], random.randint(1, 5), datetime.now() + timedelta(hours=random.randint(0, 48))),
    )
    cq_count += 1

print(f"Created {cq_count} call queue entries")

# =============================================================================
# Knowledge Base
# =============================================================================
KB_DOCS = [
    ("RBI Fair Practices Code - Debt Collection", "As per RBI guidelines, debt collection agents must: (1) Not resort to intimidation or harassment, (2) Not make calls at unreasonable hours (before 8am or after 7pm), (3) Not use threatening or abusive language, (4) Identify themselves and the purpose of the call, (5) Maintain confidentiality of customer information. Violation can result in penalties up to Rs. 1 crore.", "compliance", "en"),
    ("RBI Collection Call Timing Rules", "Collection calls must only be made between 8:00 AM and 7:00 PM. Weekend calls are permissible but should be limited. No calls on national holidays.", "compliance", "en"),
    ("Customer Privacy and Data Protection", "Customer financial data must not be shared with any third party without explicit written consent. Call recordings must be stored securely and retained for a minimum of 7 years.", "compliance", "en"),
    ("RBI Guidelines on Penal Charges", "Penal charges must be reasonable and non-discriminatory. Penal interest cannot be added to the loan balance for further interest computation.", "compliance", "en"),
    ("EMI Restructuring Policy", "Customers facing genuine financial hardship may be eligible for EMI restructuring. Eligibility: (1) Min 6 months regular payments before default, (2) Demonstrated change in financial circumstances, (3) No prior restructuring in last 12 months.", "restructuring", "en"),
    ("Partial Payment Guidelines", "Partial payments accepted and credited to oldest outstanding EMI first. Minimum: 25% of one EMI amount.", "payment", "en"),
    ("EMI Holiday / Moratorium Policy", "EMI holiday of up to 3 months for exceptional circumstances. Interest continues to accrue. Total tenure may extend.", "restructuring", "en"),
    ("Pre-closure and Foreclosure Policy", "No pre-closure charges for floating rate loans per RBI. Fixed rate: up to 2% of outstanding principal.", "payment", "en"),
    ("Escalation Protocol - Level 1", "If customer requests supervisor: (1) Acknowledge professionally, (2) Summarize context, (3) Offer callback within 4 hours, (4) Record reason.", "escalation", "en"),
    ("Escalation Protocol - Level 2 (Legal/Regulatory)", "If customer mentions legal action, consumer forum, RBI complaint, ombudsman: (1) Stay calm, (2) Take seriously, (3) Provide grievance email/phone, (4) Escalate to compliance.", "escalation", "en"),
    ("Dispute Resolution Process", "If customer disputes amount: (1) Offer detailed statement, (2) Note specific items, (3) Escalate to ops, (4) Pause collection for 7 days.", "escalation", "en"),
    ("Standard Greeting Script - Hindi", "Namaste, main VaaniSeva se [Agent Name] bol raha/rahi hoon. Kya main [Customer Name] ji se baat kar sakta/sakti hoon?", "script", "hi"),
    ("Standard Greeting Script - English", "Good [morning/afternoon], this is [Agent Name] calling from VaaniSeva. May I speak with [Customer Name] please?", "script", "en"),
    ("Standard Greeting Script - Tamil", "Vanakkam, naan VaaniSeva-yil irunthu [Agent Name] pesuren. [Customer Name] avargalai pesalama?", "script", "ta"),
    ("Payment Negotiation Framework", "Offer in priority: (1) Immediate full payment, (2) Partial now + rest in 7 days, (3) Two installments in 30 days, (4) EMI restructuring.", "negotiation", "en"),
    ("Late Fee Waiver Authority", "Level 1: up to Rs.500. Supervisor: Rs.500-2000. Regional Manager: above Rs.2000. Only for immediate payment.", "negotiation", "en"),
    ("Hardship Assessment Checklist", "Assess: (1) Employment status, (2) Medical emergency, (3) Natural disaster, (4) Other income, (5) Recovery timeline.", "negotiation", "en"),
    ("Call Closing - Successful", "Dhanyavaad [Name] ji. Toh hum confirm karte hain: [summarize]. Confirmation SMS bheja jayega.", "script", "en"),
    ("Call Closing - No Resolution", "Main samajhta/samajhti hoon. Hum [X] din mein dobara call karenge.", "script", "en"),
    ("Call Closing - Escalation", "Senior team aapko [timeframe] mein call karenge. Kya yeh number sahi hai?", "script", "en"),
    ("Personal Loan Features", "Rs.50,000 to Rs.25,00,000. Tenure: 12-60 months. Interest: 10.49%-24% p.a. No collateral.", "product", "en"),
    ("Home Loan Features", "Rs.5,00,000 to Rs.5,00,00,000. Tenure: up to 30 years. Interest: 8.40%-11.50%. Tax benefits Sec 80C/24(b).", "product", "en"),
    ("Car Loan Features", "Up to 90% on-road price (new), 70% (used). Tenure: 12-84 months. Interest: 7.99%-15%.", "product", "en"),
    ("Do's and Don'ts for Collection Agents", "DO: Be polite, verify identity, listen, offer solutions, document. DON'T: Abuse, call before 8am/after 7pm, discuss with family, promise unauthorized waivers.", "compliance", "en"),
    ("NBFC Code of Conduct", "Comply with: RBI Master Direction, Fair Practices Code, Customer Rights Charter, Digital Lending Guidelines.", "compliance", "en"),
    ("Payment Channels Available", "Online portal, Mobile app, UPI, NACH/ECS, Branch, Cheque/DD. Digital payments reflect within 24 hours.", "payment", "en"),
    ("Customer Complaint Handling", "Acknowledge within 24 hours. General: 3 days. Disputes: 7 days. Escalated: 14 days. Ombudsman: 30 days.", "compliance", "en"),
    ("Credit Score Impact Advisory", "1-30 days: minor. 31-60: moderate. 61-90: SMA. 90+: NPA, 7+ years impact.", "product", "en"),
    ("Settlement/OTS Policy", "For NPAs >90 days. Typical: 70-85% of outstanding. Branch Mgr: up to 5L. Regional: up to 25L.", "negotiation", "en"),
    ("Loan Insurance", "Optional credit life insurance available. Premium can be added to EMI. Covers outstanding in case of death/disability.", "product", "en"),
    ("Digital Lending Guidelines", "Per RBI 2022: (1) All digital loans must have KYC, (2) Cooling-off period for cancellation, (3) Clear fee disclosure, (4) No automatic increase in credit limit.", "compliance", "en"),
]

for title, content, category, lang in KB_DOCS:
    conn.execute(
        "INSERT INTO knowledge_base (title, content, category, language) VALUES (%s,%s,%s,%s)",
        (title, content, category, lang),
    )

print(f"Created {len(KB_DOCS)} knowledge base documents")

# =============================================================================
# Summary
# =============================================================================
print("\n--- Data Summary ---")
for table in ["customer_profiles", "loan_accounts", "payment_history", "call_queue", "knowledge_base"]:
    count = conn.execute(f"SELECT COUNT(*) as c FROM {table}").fetchone()["c"]
    print(f"  {table}: {count} rows")

conn.close()
print("\nDone!")
