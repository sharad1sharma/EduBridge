from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.constants import Branch, Role
from accounts.models import User
from dashboards.models import (
    AcademicBranch,
    Assessment,
    AssessmentAttempt,
    LearningResource,
    Meeting,
    PlatformNotification,
    PlatformSetting,
    Scholarship,
    Subject,
)


class Command(BaseCommand):
    help = "Seed initial academic branches, subjects, scholarships, and educational records."

    def handle(self, *args, **options):
        self.stdout.write("Seeding academic branches...")
        branch_data = [
            ("CSE", "Computer Science and Engineering", "Core computing, data structures, algorithms, AI systems."),
            ("IT", "Information Technology", "Enterprise web development, cybersecurity, cloud computing."),
            ("AIDS", "Artificial Intelligence and Data Science", "Machine learning, neural networks, big data analytics."),
            ("ECE", "Electronics and Communication Engineering", "Digital signal processing, VLSI design, embedded systems."),
            ("EE", "Electrical Engineering", "Power systems, electrical machines, control engineering."),
            ("ME", "Mechanical Engineering", "Thermodynamics, robotics, CAD/CAM, fluid mechanics."),
            ("CE", "Civil Engineering", "Structural engineering, surveying, environmental engineering."),
            ("CHE", "Chemical Engineering", "Process dynamics, chemical reaction engineering, heat transfer."),
            ("BT", "Biotechnology", "Genomics, bioprocess engineering, bioinformatics."),
            ("AE", "Aerospace Engineering", "Aerodynamics, flight mechanics, propulsion systems."),
            ("FY", "Common first-year engineering", "Foundational mathematics, physics, engineering graphics."),
        ]
        for code, name, desc in branch_data:
            AcademicBranch.objects.get_or_create(code=code, defaults={"name": name, "description": desc})

        self.stdout.write("Seeding subjects...")
        teacher = User.objects.filter(role=Role.TEACHER.value).first()
        subjects_data = [
            ("CS301", "Design & Analysis of Algorithms", "CSE", 3, 4.0, False, "Divide & conquer, greedy, dynamic programming, graph algorithms."),
            ("CS302", "Operating Systems", "CSE", 3, 4.0, False, "Process scheduling, synchronization, paging, file systems."),
            ("CS304", "Database Management Systems", "CSE", 4, 4.0, False, "ER modeling, relational algebra, SQL, normalization (3NF/BCNF), ACID transactions."),
            ("CS401", "Computer Networks", "CSE", 4, 3.5, False, "OSI model, TCP/IP, routing protocols, flow & congestion control."),
            ("AI301", "Introduction to Machine Learning", "AIDS", 3, 4.0, False, "Supervised & unsupervised learning, gradient descent, regression, SVMs."),
            ("EC201", "Signals & Systems", "ECE", 3, 4.0, False, "Fourier transform, Laplace transform, z-transform, linear time-invariant systems."),
            ("ME201", "Engineering Thermodynamics", "ME", 3, 4.0, False, "First and second laws, Carnot cycles, entropy, steam tables."),
            ("FY101", "Engineering Mathematics I", "FY", 1, 4.0, False, "Matrices, eigenvalues, multivariable calculus, Taylor series."),
        ]
        created_subjects = {}
        for code, title, branch, sem, creds, elec, syllabus in subjects_data:
            s, _ = Subject.objects.get_or_create(
                code=code,
                defaults={
                    "title": title, "branch": branch, "semester": sem,
                    "credits": creds, "is_elective": elec, "syllabus_summary": syllabus
                }
            )
            if teacher:
                s.assigned_teachers.add(teacher)
            created_subjects[code] = s

        self.stdout.write("Seeding scholarships (Admin only)...")
        now = timezone.now().date()
        scholarships_data = [
            (
                "Merit-Cum-Means Engineering Excellence Grant",
                "Ministry of Education, Government of India",
                "Financial assistance for meritorious undergraduate engineering students from economically weaker sections.",
                "B.Tech Undergraduate", "All Branches", "1st to 4th Year", "Annual family income < 4.5 LPA",
                7.50, "Income certificate, 10+2 marksheet, College bonafide",
                now - timedelta(days=20), now + timedelta(days=28),
                "https://scholarships.gov.in/", "https://www.education.gov.in/",
            ),
            (
                "National Tech Women in STEM Fellowship",
                "All India Council for Technical Education (AICTE)",
                "Pre-final and final year grant for female engineering scholars pursuing AI, robotics, or semiconductor research.",
                "B.Tech 3rd & 4th Year", "CSE, IT, AIDS, ECE", "3rd to 4th Year", "No income ceiling",
                8.00, "Semester grade sheets, Project abstract, Recommendation letter",
                now - timedelta(days=15), now + timedelta(days=45),
                "https://www.aicte-india.org/", "https://www.aicte-india.org/schemes/students-development-schemes",
            ),
            (
                "Industry Innovation B.Tech Research Subsidy",
                "Federation of Indian Chambers of Commerce & Industry",
                "Direct research grant for industrial engineering capstone and patent development projects.",
                "B.Tech Final Year", "CSE, ECE, ME, EE", "4th Year", "Annual family income < 8.0 LPA",
                7.00, "Detailed project proposal, Faculty endorsement, Expense forecast",
                now - timedelta(days=5), now + timedelta(days=12),
                "https://www.ficci.in/", "https://www.ficci.in/initiatives",
            ),
        ]
        for name, prov, desc, ed_lvl, br, yr, inc, cgpa, docs, op_dt, dl, app_url, src_url in scholarships_data:
            Scholarship.objects.get_or_create(
                name=name,
                defaults={
                    "provider": prov, "description": desc, "education_level": ed_lvl,
                    "eligible_branches": br, "academic_year": yr, "income_criteria": inc,
                    "min_cgpa": cgpa, "required_documents": docs, "opening_date": op_dt,
                    "deadline": dl, "official_application_url": app_url,
                    "official_source_url": src_url, "status": Scholarship.Status.PUBLISHED
                }
            )

        self.stdout.write("Seeding sample assessments (Daily assignment >= 10 MCQs, Weekly test = 25 MCQs + 5 Coding)...")
        # 1. Daily Assignment (10 MCQs)
        daily_mcqs = [
            {"id": i, "question": f"What is the time complexity of operation {i} in a Red-Black Tree?",
             "options": ["O(1)", "O(log n)", "O(n)", "O(n log n)"], "correct": "B", "marks": 2}
            for i in range(1, 11)
        ]
        algo_sub = created_subjects.get("CS301")
        now_dt = timezone.now()
        ass1, _ = Assessment.objects.get_or_create(
            title="Daily Practice 04: Red-Black Tree Balance & Invariants",
            assessment_type=Assessment.AssessmentType.DAILY_ASSIGNMENT,
            branch="CSE", semester=3,
            defaults={
                "subject": algo_sub, "created_by": teacher,
                "description": "Daily MCQ assessment covering binary search trees, node coloring, and rotation invariants.",
                "duration_minutes": 20, "total_marks": 20,
                "deadline": now_dt + timedelta(days=3),
                "questions_data": daily_mcqs, "coding_problems_data": [],
                "status": Assessment.Status.PUBLISHED
            }
        )

        # 2. Weekly Test (25 MCQs + 5 Coding problems)
        weekly_mcqs = [
            {"id": i, "question": f"Database normalization question {i}: Which normal form eliminates transitive dependency?",
             "options": ["1NF", "2NF", "3NF", "BCNF"], "correct": "C", "marks": 3}
            for i in range(1, 26)
        ]
        coding_problems = [
            {"id": 1, "title": "Implement Dijkstra Shortest Path", "description": "Given an adjacency list, find shortest paths.", "sample_input": "4 5\\n1 2 2", "sample_output": "[0, 2, 4, 5]"},
            {"id": 2, "title": "Longest Increasing Subsequence", "description": "Find the length of the longest subsequence in O(n log n).", "sample_input": "[10,9,2,5,3,7,101,18]", "sample_output": "4"},
            {"id": 3, "title": "LRU Cache Implementation", "description": "Design a data structure that follows Least Recently Used cache constraints.", "sample_input": "capacity=2", "sample_output": "1, -1, 3"},
            {"id": 4, "title": "Merge K Sorted Linked Lists", "description": "Merge k sorted linked lists and return it as one sorted list.", "sample_input": "[[1,4,5],[1,3,4],[2,6]]", "sample_output": "[1,1,2,3,4,4,5,6]"},
            {"id": 5, "title": "Minimum Spanning Tree (Kruskal)", "description": "Compute the minimum weight to connect all vertices.", "sample_input": "V=4, E=5", "sample_output": "19"}
        ]
        db_sub = created_subjects.get("CS304")
        ass2, _ = Assessment.objects.get_or_create(
            title="Weekly Test 03: Algorithms & Relational Algebra",
            assessment_type=Assessment.AssessmentType.WEEKLY_TEST,
            branch="CSE", semester=3,
            defaults={
                "subject": db_sub, "created_by": teacher,
                "description": "Comprehensive weekly benchmark consisting of 25 conceptual MCQs and 5 coding evaluations.",
                "duration_minutes": 120, "total_marks": 100,
                "deadline": now_dt + timedelta(days=7),
                "questions_data": weekly_mcqs, "coding_problems_data": coding_problems,
                "status": Assessment.Status.PUBLISHED
            }
        )

        # Record student attempts if student exists
        student = User.objects.filter(role=Role.STUDENT.value).first()
        if student:
            AssessmentAttempt.objects.get_or_create(
                assessment=ass1, student=student,
                defaults={
                    "score": 18.0, "status": AssessmentAttempt.AttemptStatus.COMPLETED,
                    "submitted_at": now_dt - timedelta(hours=2),
                    "answers": {"1": "B", "2": "B", "3": "B", "4": "B", "5": "B", "6": "B", "7": "B", "8": "B", "9": "B", "10": "A"}
                }
            )

        self.stdout.write("Seeding learning resources...")
        resources_data = [
            ("Advanced Graph Algorithms & Maximum Flow", "Complete lecture notes on Ford-Fulkerson, Edmonds-Karp, and Min-Cut theorem.", "CSE", 3, algo_sub, "Graph Algorithms", LearningResource.ResourceType.PDF, "https://www.geeksforgeeks.org/max-flow-problem-introduction/"),
            ("Operating Systems Process Scheduling & Memory Lab Manual", "Laboratory manual with C exercises implementing round robin and paging simulations.", "CSE", 3, created_subjects.get("CS302"), "OS Lab", LearningResource.ResourceType.LAB_MANUAL, "https://os.eecs.harvard.edu/"),
            ("Database Normalization (1NF to BCNF) Masterclass", "Curated institutional video series explaining functional dependencies and loss-less decompositions.", "CSE", 4, db_sub, "Normalization", LearningResource.ResourceType.VIDEO, "https://www.youtube.com/watch?v=GFQaEYEc8_8"),
        ]
        for title, desc, br, sem, sub, topic, r_type, url in resources_data:
            LearningResource.objects.get_or_create(
                title=title,
                defaults={
                    "description": desc, "branch": br, "semester": sem,
                    "subject": sub, "topic": topic, "resource_type": r_type,
                    "external_url": url, "author": teacher,
                    "status": LearningResource.Status.PUBLISHED, "download_count": 84
                }
            )

        self.stdout.write("Seeding scheduled meetings...")
        if teacher:
            Meeting.objects.get_or_create(
                title="CSE 3rd Sem Algorithms Tutorial & Doubt Session",
                host_teacher=teacher,
                defaults={
                    "description": "Weekly interactive doubt clearing and problem breakdown session on Dynamic Programming.",
                    "branch": "CSE", "semester": 3, "subject": algo_sub,
                    "scheduled_at": now_dt + timedelta(days=1, hours=3),
                    "duration_minutes": 60, "meeting_link": "https://meet.google.com/edu-algo-sync",
                    "status": Meeting.Status.SCHEDULED
                }
            )

        self.stdout.write("Seeding platform settings...")
        settings_data = [
            ("platform_name", "EduBridge B.Tech Suite", "Official platform brand title"),
            ("academic_year_active", "2026-2027", "Current academic registration year"),
            ("auto_submit_enabled", "true", "Enforce automatic assessment deadline finalization"),
            ("audit_retention_days", "365", "Number of days security audit events are retained"),
            ("ai_admin_assistant_enabled", "true", "Enable EduBridge Admin AI intelligence assistant"),
        ]
        for k, v, d in settings_data:
            PlatformSetting.objects.get_or_create(key=k, defaults={"value": v, "description": d})

        self.stdout.write(self.style.SUCCESS("EduBridge academic data seeded successfully!"))
