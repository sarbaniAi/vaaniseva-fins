# Databricks notebook source
# MAGIC %md
# MAGIC # VaaniSeva — Synthetic Data Generation
# MAGIC Generates 50 customers, 80 loans, 30 call queue entries, and 30+ knowledge base documents.

# COMMAND ----------

# MAGIC %pip install databricks-sdk psycopg[binary] psycopg_pool
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

import os, uuid, time, random, json
from datetime import datetime, timedelta
from threading import Lock
from databricks.sdk import WorkspaceClient
import psycopg
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

# COMMAND ----------

# Configuration — MUST MATCH 00_setup_lakebase
INSTANCE_NAME = "vaaniseva-lakebase"
CONN_HOST = ""  # Your Lakebase host
DB_NAME = "vaaniseva"

# COMMAND ----------

# Connection setup (same pattern as 00_setup_lakebase)
class CredentialConnection(psycopg.Connection):
    workspace_client = None
    instance_name = None
    _cached_credential = None
    _cache_timestamp = None
    _cache_duration = 3000
    _cache_lock = Lock()

    @classmethod
    def connect(cls, conninfo="", **kwargs):
        kwargs["password"] = cls._get_cached_credential()
        return super().connect(conninfo, **kwargs)

    @classmethod
    def _get_cached_credential(cls):
        with cls._cache_lock:
            now = time.time()
            if cls._cached_credential and cls._cache_timestamp and now - cls._cache_timestamp < cls._cache_duration:
                return cls._cached_credential
            credential = cls.workspace_client.database.generate_database_credential(
                request_id=str(uuid.uuid4()), instance_names=[cls.instance_name]
            )
            cls._cached_credential = credential.token
            cls._cache_timestamp = now
            return cls._cached_credential

w = WorkspaceClient()
CredentialConnection.workspace_client = w
CredentialConnection.instance_name = INSTANCE_NAME
try:
    username = w.current_service_principal.me().application_id
except:
    username = w.current_user.me().user_name

pool = ConnectionPool(
    conninfo=f"dbname={DB_NAME} user={username} host={CONN_HOST} sslmode=require",
    connection_class=CredentialConnection,
    min_size=1, max_size=5, timeout=30.0, open=True,
    kwargs={"autocommit": True, "row_factory": dict_row}
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Generate Customer Profiles

# COMMAND ----------

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

LANGUAGES = ["hi", "en", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa"]
LANG_BY_CITY = {
    "Mumbai": "mr", "Delhi": "hi", "Bangalore": "kn", "Chennai": "ta",
    "Hyderabad": "te", "Pune": "mr", "Kolkata": "bn", "Ahmedabad": "gu",
    "Jaipur": "hi", "Lucknow": "hi", "Chandigarh": "pa", "Bhopal": "hi",
    "Indore": "hi", "Coimbatore": "ta", "Nagpur": "mr", "Vadodara": "gu",
    "Kochi": "ml", "Visakhapatnam": "te", "Patna": "hi", "Ranchi": "hi",
}

RISK_TIERS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

customers = []
with pool.connection() as conn:
    # Clear existing data
    conn.execute("DELETE FROM call_queue")
    conn.execute("DELETE FROM quality_scores")
    conn.execute("DELETE FROM call_logs")
    conn.execute("DELETE FROM loan_accounts")
    conn.execute("DELETE FROM knowledge_base")
    conn.execute("DELETE FROM customer_profiles")

    for i, name in enumerate(INDIAN_NAMES):
        city = random.choice(CITIES)
        lang = LANG_BY_CITY.get(city, random.choice(LANGUAGES))
        phone = f"+91{random.randint(70000, 99999)}{random.randint(10000, 99999)}"
        last4 = f"{random.randint(1000, 9999)}"
        risk = random.choice(RISK_TIERS)

        conn.execute(
            """INSERT INTO customer_profiles (name, phone, city, language_pref, account_last4, risk_tier)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (name, phone, city, lang, last4, risk)
        )

    customers = conn.execute("SELECT * FROM customer_profiles ORDER BY id").fetchall()
    print(f"Created {len(customers)} customers")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Generate Loan Accounts

# COMMAND ----------

LOAN_TYPES = ["Personal Loan", "Home Loan", "Car Loan", "Education Loan", "Business Loan", "Gold Loan"]

loan_count = 0
with pool.connection() as conn:
    for cust in customers:
        # 1-3 loans per customer
        n_loans = random.choices([1, 2, 3], weights=[0.5, 0.35, 0.15])[0]
        for _ in range(n_loans):
            loan_type = random.choice(LOAN_TYPES)
            principal = random.choice([50000, 100000, 200000, 500000, 1000000, 2000000, 5000000])
            emi = round(principal * random.uniform(0.015, 0.04), 2)
            days_overdue = random.choices(
                [0, random.randint(1, 15), random.randint(16, 45), random.randint(46, 90), random.randint(91, 180)],
                weights=[0.3, 0.25, 0.2, 0.15, 0.1]
            )[0]
            overdue = round(emi * max(1, days_overdue // 30), 2) if days_overdue > 0 else 0
            last_pay = (datetime.now() - timedelta(days=days_overdue + random.randint(0, 30))).date() if days_overdue > 0 else (datetime.now() - timedelta(days=random.randint(1, 28))).date()

            conn.execute(
                """INSERT INTO loan_accounts (customer_id, loan_type, principal, emi_amount, overdue_amount, days_overdue, last_payment_date)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (cust["id"], loan_type, principal, emi, overdue, days_overdue, last_pay)
            )
            loan_count += 1

    print(f"Created {loan_count} loans")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Generate Call Queue

# COMMAND ----------

with pool.connection() as conn:
    # Queue customers with overdue loans
    overdue_customers = conn.execute(
        "SELECT DISTINCT customer_id FROM loan_accounts WHERE days_overdue > 0 ORDER BY customer_id"
    ).fetchall()

    count = 0
    for oc in overdue_customers[:30]:
        priority = random.randint(1, 5)
        scheduled = datetime.now() + timedelta(hours=random.randint(0, 48))
        conn.execute(
            """INSERT INTO call_queue (customer_id, priority, scheduled_at, status)
               VALUES (%s, %s, %s, 'PENDING')""",
            (oc["customer_id"], priority, scheduled)
        )
        count += 1

    print(f"Created {count} call queue entries")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Generate Knowledge Base Documents

# COMMAND ----------

KB_DOCS = [
    # RBI Fair Practices
    ("RBI Fair Practices Code - Debt Collection", "As per RBI guidelines, debt collection agents must: (1) Not resort to intimidation or harassment, (2) Not make calls at unreasonable hours (before 8am or after 7pm), (3) Not use threatening or abusive language, (4) Identify themselves and the purpose of the call, (5) Maintain confidentiality of customer information, (6) Not disclose debt information to unauthorized third parties. Violation can result in penalties up to Rs. 1 crore.", "compliance", "en"),
    ("RBI Collection Call Timing Rules", "Collection calls must only be made between 8:00 AM and 7:00 PM. Weekend calls are permissible but should be limited. No calls on national holidays. If the customer requests a specific time for callback, it must be honored within 48 hours.", "compliance", "en"),
    ("Customer Privacy and Data Protection", "Customer financial data must not be shared with any third party without explicit written consent. Call recordings must be stored securely and retained for a minimum of 7 years. Agent must verify customer identity before discussing any account details.", "compliance", "en"),
    ("RBI Guidelines on Penal Charges", "As per RBI circular dated August 18, 2023, penal charges must be reasonable and non-discriminatory. Penal interest cannot be added to the loan balance for further interest computation. All penal charges must be clearly communicated to the borrower upfront.", "compliance", "en"),

    # EMI Restructuring
    ("EMI Restructuring Policy", "Customers facing genuine financial hardship may be eligible for EMI restructuring. Eligibility criteria: (1) Minimum 6 months of regular payments before default, (2) Demonstrated change in financial circumstances (job loss, medical emergency, natural disaster), (3) No prior restructuring in the last 12 months. Process: Customer submits application → Credit team review (2-3 business days) → Approval/rejection → New EMI schedule.", "restructuring", "en"),
    ("Partial Payment Guidelines", "Partial payments are accepted and credited to the oldest outstanding EMI first. Minimum partial payment: 25% of one EMI amount. Partial payment does not stop collection calls but changes the urgency level. Customer should be informed of the remaining balance and next due date after partial payment.", "payment", "en"),
    ("EMI Holiday / Moratorium Policy", "EMI holiday of up to 3 months may be granted in exceptional circumstances (medical emergency with supporting documents, natural disaster in customer's area). Interest continues to accrue during the moratorium period. Total loan tenure may be extended. Customer must apply in writing with supporting documentation.", "restructuring", "en"),
    ("Pre-closure and Foreclosure Policy", "Customers may pre-close their loan at any time. No pre-closure charges for floating rate loans as per RBI guidelines. Fixed rate loans: Pre-closure charge of up to 2% of outstanding principal. Foreclosure statement provided within 7 business days of request.", "payment", "en"),

    # Escalation Protocols
    ("Escalation Protocol - Level 1", "If the customer requests to speak with a supervisor or expresses strong dissatisfaction: (1) Acknowledge the request professionally, (2) Summarize the call context, (3) Offer a callback from the supervisor within 4 business hours, (4) Record the escalation reason in the system, (5) Do not argue or refuse the escalation request.", "escalation", "en"),
    ("Escalation Protocol - Level 2 (Legal/Regulatory)", "If the customer mentions legal action, consumer forum, RBI complaint, or ombudsman: (1) Remain calm and professional, (2) Inform that all regulatory complaints are taken seriously, (3) Provide the company's grievance redressal email and phone number, (4) Immediately escalate to the compliance team, (5) Document the call thoroughly.", "escalation", "en"),
    ("Dispute Resolution Process", "If a customer disputes the outstanding amount: (1) Offer to send a detailed statement via email/SMS, (2) Note the specific items disputed, (3) Escalate to the operations team for verification, (4) Pause collection calls for the disputed amount for 7 days, (5) Inform the customer of the resolution timeline (5-7 business days).", "escalation", "en"),

    # Greeting Scripts
    ("Standard Greeting Script - Hindi", "Namaste, main VaaniSeva se [Agent Name] bol raha/rahi hoon. Kya main [Customer Name] ji se baat kar sakta/sakti hoon? [Wait for confirmation] Security ke liye, kya aap apne account ke last 4 digits bata sakte hain? [After verification] Dhanyavaad. Main aapko aapke [Loan Type] account ke baare mein call kar raha/rahi hoon.", "script", "hi"),
    ("Standard Greeting Script - English", "Good [morning/afternoon], this is [Agent Name] calling from VaaniSeva. May I speak with [Customer Name] please? [Wait for confirmation] For security purposes, could you please confirm the last 4 digits of your account number? [After verification] Thank you. I'm calling regarding your [Loan Type] account.", "script", "en"),
    ("Standard Greeting Script - Tamil", "Vanakkam, naan VaaniSeva-yil irunthu [Agent Name] pesuren. [Customer Name] avargalai pesalama? [Verification] Paathukaapu kaaga, ungal account-in kadaisi 4 elakangalai sollunga. [After verification] Nandri. Ungal [Loan Type] loan pathi pesavae call pannuren.", "script", "ta"),

    # Negotiation Guidelines
    ("Payment Negotiation Framework", "Offer resolution options in this priority order: (1) Immediate full payment - best for customer's credit score, (2) Partial payment now + commitment for remaining within 7 days, (3) Two-installment plan within 30 days, (4) EMI restructuring application (for genuine hardship cases). Agent should understand the customer's situation before suggesting options. Never pressure or threaten. Emphasize the benefits of resolution (credit score improvement, cessation of collection activity).", "negotiation", "en"),
    ("Late Fee Waiver Authority", "Agents at Level 1 can waive late fees up to Rs. 500. Late fees between Rs. 500-2000 require supervisor approval. Late fees above Rs. 2000 require regional manager approval. Late fee waiver should only be offered as an incentive for immediate or same-day payment. Document all waiver authorizations.", "negotiation", "en"),
    ("Hardship Assessment Checklist", "When a customer claims financial hardship, assess: (1) Employment status - recently unemployed? (2) Medical emergency - self or family? (3) Natural disaster impact? (4) Other income sources? (5) Expected timeline for recovery? Based on assessment, recommend appropriate resolution (payment plan, restructuring, or moratorium).", "negotiation", "en"),

    # Closing Scripts
    ("Call Closing - Successful Resolution", "Thank the customer: 'Dhanyavaad [Name] ji. Toh hum confirm karte hain: [summarize agreed action]. Aapko ek confirmation SMS/email bheja jayega. Agar koi aur sahayta chahiye toh humse sampark zaroor karein. Aapka din shubh ho!'", "script", "en"),
    ("Call Closing - No Resolution", "If no resolution reached: 'Main samajhta/samajhti hoon [Name] ji. Aapki situation samajh mein aayi. Hum aapko [X] din mein dobara call karenge. Tab tak agar aap payment kar paye toh online portal ya nearest branch mein kar sakte hain. Koi bhi madad chahiye toh humse contact karein. Dhanyavaad.'", "script", "en"),
    ("Call Closing - Escalation", "After escalation: '[Name] ji, main aapki baat senior team tak pahuncha dunga/dungi. Woh aapko [timeframe] mein call karenge. Kya aapka yeh number sahi hai callback ke liye? [Confirm number] Dhanyavaad, aapke patience ke liye shukriya.'", "script", "en"),

    # Product Information
    ("Personal Loan Features", "Personal loans from Rs. 50,000 to Rs. 25,00,000. Tenure: 12-60 months. Interest rates: 10.49% - 24% per annum based on credit profile. No collateral required. EMI starts from the next month after disbursement. Pre-closure allowed after 6 months.", "product", "en"),
    ("Home Loan Features", "Home loans from Rs. 5,00,000 to Rs. 5,00,00,000. Tenure: up to 30 years. Interest rates: 8.40% - 11.50% per annum. Property insurance mandatory. Tax benefits under Section 80C and 24(b). Balance transfer facility available.", "product", "en"),
    ("Car Loan Features", "Car loans for new and used vehicles. Amount: Up to 90% of on-road price (new), 70% (used). Tenure: 12-84 months. Interest rates: 7.99% - 15% per annum. Hypothecation of vehicle required. Insurance mandatory.", "product", "en"),

    # Compliance Training
    ("Do's and Don'ts for Collection Agents", "DO: Be polite and professional at all times. DO: Verify customer identity before sharing details. DO: Listen to customer concerns. DO: Offer viable solutions. DO: Document every call. DON'T: Use abusive or threatening language. DON'T: Call before 8am or after 7pm. DON'T: Discuss debt with family members. DON'T: Promise unauthorized waivers. DON'T: Misrepresent yourself or the company.", "compliance", "en"),
    ("NBFC Code of Conduct", "All collection activities must comply with: (1) RBI Master Direction on NBFC, (2) Fair Practices Code, (3) Customer Rights Charter, (4) Digital Lending Guidelines, (5) Grievance Redressal Framework. Annual compliance training is mandatory for all agents.", "compliance", "en"),

    # Additional policies
    ("Payment Channels Available", "Customers can make payments through: (1) Online portal at payments.example.com, (2) Mobile app, (3) UPI (VPA: emi@examplebank), (4) NACH/ECS auto-debit mandate, (5) Nearest branch or authorized collection center, (6) Cheque/DD payable to the company. All digital payments reflect within 24 hours.", "payment", "en"),
    ("Customer Complaint Handling", "All complaints must be acknowledged within 24 hours. Resolution timeline: (1) General queries: 3 business days, (2) Account disputes: 7 business days, (3) Escalated complaints: 14 business days, (4) Ombudsman complaints: 30 business days. Complaint reference number must be provided to the customer.", "compliance", "en"),
    ("Credit Score Impact Advisory", "Overdue EMIs impact credit score (CIBIL/Experian/Equifax). 1-30 days overdue: Minor impact, can recover in 3-6 months. 31-60 days: Moderate impact, may affect future loan approvals. 61-90 days: Significant impact, reported as 'Special Mention Account'. 90+ days: NPA classification, major credit impact lasting 7+ years.", "product", "en"),
    ("Settlement and One-Time Payment Offers", "One-time settlement (OTS) may be offered for NPAs > 90 days. Typical OTS: 70-85% of outstanding amount. OTS authority: Branch Manager up to Rs. 5 lakh, Regional Manager up to Rs. 25 lakh, Central Credit Committee above Rs. 25 lakh. Settlement is reported to credit bureaus as 'Settled' (not 'Closed').", "negotiation", "en"),
]

with pool.connection() as conn:
    for title, content, category, lang in KB_DOCS:
        conn.execute(
            "INSERT INTO knowledge_base (title, content, category, language) VALUES (%s, %s, %s, %s)",
            (title, content, category, lang)
        )
    print(f"Created {len(KB_DOCS)} knowledge base documents")

# COMMAND ----------

# Verify data counts
with pool.connection() as conn:
    for table in ["customer_profiles", "loan_accounts", "call_queue", "knowledge_base"]:
        count = conn.execute(f"SELECT COUNT(*) as c FROM {table}").fetchone()
        print(f"{table}: {count['c']} rows")

# COMMAND ----------

pool.close()
print("Synthetic data generation complete!")
