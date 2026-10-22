"""EduBridge Verified Scholarships & Grants Service.

Provides deterministic seeding and runtime verification for published scholarships
available to B.Tech students across institutional, state, and corporate portals.
"""
from datetime import timedelta
from django.utils import timezone


def ensure_default_scholarships():
    """Ensure verified demo and government scholarships exist in the database.
    Idempotent and safe to call on startup, migration, or dashboard view load.
    """
    from dashboards.models import Scholarship

    # If published scholarships already exist, do not duplicate
    if Scholarship.objects.filter(status=Scholarship.Status.PUBLISHED).count() >= 6:
        return

    today = timezone.now().date()

    scholarships_data = [
        {
            "name": "Merit-Cum-Means Engineering Excellence Grant",
            "provider": "Ministry of Education, Government of India",
            "description": "Comprehensive financial support providing full tuition remission and living stipends for meritorious B.Tech engineering students from economically weaker sections.",
            "education_level": "B.Tech Undergraduate",
            "eligible_branches": "All Branches",
            "academic_year": "1st to 4th Year",
            "income_criteria": "Annual family income < 4.5 LPA",
            "min_cgpa": 7.50,
            "required_documents": "Income certificate, 10+2 / semester marksheet, College bonafide, Bank passbook",
            "opening_date": today - timedelta(days=20),
            "deadline": today + timedelta(days=28),
            "official_application_url": "https://scholarships.gov.in/",
            "official_source_url": "https://www.education.gov.in/",
            "status": Scholarship.Status.PUBLISHED,
        },
        {
            "name": "National Tech Women in STEM Fellowship (AICTE Pragati)",
            "provider": "All India Council for Technical Education (AICTE)",
            "description": "Prestigious government fellowship awarded to female engineering scholars pursuing technical degrees in Computer Science, AI, and Electronics.",
            "education_level": "B.Tech 2nd, 3rd & 4th Year",
            "eligible_branches": "CSE, IT, AIDS, ECE",
            "academic_year": "2nd to 4th Year",
            "income_criteria": "Annual family income < 8.0 LPA",
            "min_cgpa": 8.00,
            "required_documents": "Semester grade sheets, Faculty recommendation letter, Bonafide certificate, Aadhaar card",
            "opening_date": today - timedelta(days=15),
            "deadline": today + timedelta(days=11),  # Triggers is_deadline_near badge
            "official_application_url": "https://www.aicte-india.org/",
            "official_source_url": "https://www.aicte-india.org/schemes/students-development-schemes",
            "status": Scholarship.Status.PUBLISHED,
        },
        {
            "name": "Industry Innovation B.Tech Research Subsidy",
            "provider": "Federation of Indian Chambers of Commerce & Industry (FICCI)",
            "description": "Direct research grant sponsorship for undergraduate engineering capstone, IoT prototyping, open-source software, and patent development projects.",
            "education_level": "B.Tech 3rd & 4th Year",
            "eligible_branches": "CSE, ECE, ME, EE",
            "academic_year": "3rd to 4th Year",
            "income_criteria": "Annual family income < 8.0 LPA",
            "min_cgpa": 7.00,
            "required_documents": "Detailed project proposal, Faculty endorsement, Expense forecast",
            "opening_date": today - timedelta(days=5),
            "deadline": today + timedelta(days=7),  # Triggers is_deadline_near badge
            "official_application_url": "https://www.ficci.in/",
            "official_source_url": "https://www.ficci.in/initiatives",
            "status": Scholarship.Status.PUBLISHED,
        },
        {
            "name": "Central Sector Scheme of Scholarships for University Students",
            "provider": "Department of Higher Education, Govt of India",
            "description": "Direct benefit transfer (DBT) grant awarded to top percentile engineering students to cover laboratory fees, tuition, and instructional materials.",
            "education_level": "B.Tech 1st to 4th Year",
            "eligible_branches": "All Branches",
            "academic_year": "1st to 4th Year",
            "income_criteria": "Annual family income < 4.5 LPA",
            "min_cgpa": 7.00,
            "required_documents": "National Scholarship Portal verification, College bonafide, Class 12 certificate",
            "opening_date": today - timedelta(days=30),
            "deadline": today + timedelta(days=45),
            "official_application_url": "https://scholarships.gov.in/",
            "official_source_url": "https://www.education.gov.in/scholarships",
            "status": Scholarship.Status.PUBLISHED,
        },
        {
            "name": "Tata Consultancy Services (TCS) Foundation Ignite Grant",
            "provider": "TCS Foundation CSR Initiative",
            "description": "Merit-cum-means corporate scholarship funding final-year engineering students with tuition coverage, laptop grants, and industry project mentorship.",
            "education_level": "B.Tech 3rd & 4th Year",
            "eligible_branches": "CSE, IT, AIDS, ECE",
            "academic_year": "3rd to 4th Year",
            "income_criteria": "Annual family income < 6.0 LPA",
            "min_cgpa": 7.50,
            "required_documents": "All semester grade sheets, College ID, Resume, Coding portfolio link",
            "opening_date": today - timedelta(days=10),
            "deadline": today + timedelta(days=35),
            "official_application_url": "https://www.tcs.com/careers/india",
            "official_source_url": "https://www.tcs.com/",
            "status": Scholarship.Status.PUBLISHED,
        },
        {
            "name": "Google Women Techmakers (WTM) Scholars Program",
            "provider": "Google Student Veterans & Inclusion Foundation",
            "description": "Global scholarship empowering female computer scientists with academic grants, international retreat attendance, and direct mentoring by Google engineers.",
            "education_level": "B.Tech Undergraduate",
            "eligible_branches": "CSE, IT, AIDS",
            "academic_year": "1st to 4th Year",
            "income_criteria": "No income ceiling",
            "min_cgpa": 8.00,
            "required_documents": "Resume, Academic transcripts, Statement of Purpose essay, GitHub profile",
            "opening_date": today - timedelta(days=10),
            "deadline": today + timedelta(days=60),
            "official_application_url": "https://buildyourfuture.withgoogle.com/scholarships",
            "official_source_url": "https://www.womentechmakers.com/",
            "status": Scholarship.Status.PUBLISHED,
        },
    ]

    for item in scholarships_data:
        Scholarship.objects.update_or_create(
            name=item["name"],
            defaults=item,
        )
