"""EduBridge Deterministic Demo Data Seeder.

Creates a consistent, comprehensive educational environment for demonstrations:
- Students, Teachers, and Admin accounts with deterministic credentials
- Subjects, explicit M2M enrollments, and syllabus details
- Realistic assessment scores, attempts, and grade trajectories
- Attendance records (Present, Absent, Late, Platform Login) across subjects
- Live classes and academic meetings
- Course notes and resources with visual thumbnails
- Coding resources (DSA questions & online compilers with verified external URLs)
- Notifications and audit logs
- Suspended account for administrative governance testing
"""
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.constants import Branch, Role
from accounts.models import AuditEvent, StudentProfile, TeacherProfile, User
from dashboards.models import (
    AcademicBranch,
    Assessment,
    AssessmentAttempt,
    AttendanceRecord,
    CodingResource,
    LearningResource,
    Meeting,
    PlatformNotification,
    PlatformSetting,
    Scholarship,
    Subject,
)


class Command(BaseCommand):
    help = "Deterministically seeds EduBridge with rich demo data for evaluation and presentations."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Reset demo records before seeding",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Initializing EduBridge Demo Dataset..."))

        now = timezone.now()
        today = now.date()

        # =====================================================================
        # 1. ACADEMIC BRANCHES
        # =====================================================================
        self.stdout.write("1. Seeding Academic Branches...")
        branches_data = [
            ("CSE", "Computer Science and Engineering", "Algorithms, Systems, Machine Learning, and Cloud Architecture."),
            ("IT", "Information Technology", "Enterprise Applications, DevOps, Web Engineering, and Cybersecurity."),
            ("AIDS", "Artificial Intelligence & Data Science", "Neural Networks, Deep Learning, Big Data Analytics."),
            ("ECE", "Electronics and Communication Engineering", "Digital Signal Processing, VLSI Design, and Embedded Systems."),
            ("EE", "Electrical Engineering", "Control Systems, Power Engineering, Smart Grid Infrastructure."),
            ("ME", "Mechanical Engineering", "Thermodynamics, Robotics, Fluid Mechanics, CAD/CAM."),
        ]
        branch_objs = {}
        for code, name, desc in branches_data:
            b, _ = AcademicBranch.objects.get_or_create(code=code, defaults={"name": name, "description": desc})
            branch_objs[code] = b

        # =====================================================================
        # 2. TEACHERS & FACULTY
        # =====================================================================
        self.stdout.write("2. Seeding Faculty Accounts...")
        teachers_data = [
            {
                "username": "prof_sharma",
                "email": "sharma@edubridge.edu",
                "full_name": "Prof. Rajesh Sharma",
                "public_id": "T2001",
                "department": "CSE",
                "designation": "Professor & Head of Department",
                "specialization": "Data Structures & Algorithm Design",
            },
            {
                "username": "prof_verma",
                "email": "verma@edubridge.edu",
                "full_name": "Dr. Sunita Verma",
                "public_id": "T2002",
                "department": "CSE",
                "designation": "Associate Professor",
                "specialization": "Operating Systems & Distributed Computing",
            },
            {
                "username": "prof_reddy",
                "email": "reddy@edubridge.edu",
                "full_name": "Prof. K. V. Reddy",
                "public_id": "T2003",
                "department": "ECE",
                "designation": "Assistant Professor",
                "specialization": "Signals, Systems & Embedded IoT",
            },
        ]
        created_teachers = {}
        for t_info in teachers_data:
            user = User.objects.filter(public_id=t_info["public_id"]).first()
            if not user:
                user = User.objects.filter(username=t_info["username"]).first()
            if not user:
                user = User(
                    username=t_info["username"],
                    public_id=t_info["public_id"],
                )
            user.full_name = t_info["full_name"]
            user.email = t_info["email"]
            user.role = Role.TEACHER.value
            user.is_active = True
            user.public_id = t_info["public_id"]
            user.set_password("Demo@12345")
            user.save()

            tp, _ = TeacherProfile.objects.get_or_create(
                user=user,
                defaults={
                    "department": t_info["department"],
                    "designation": t_info["designation"],
                    "bio": f"Specialization: {t_info['specialization']}",
                }
            )
            created_teachers[t_info["username"]] = user

        primary_teacher = created_teachers["prof_sharma"]
        secondary_teacher = created_teachers["prof_verma"]

        # =====================================================================
        # 3. CORE SUBJECTS
        # =====================================================================
        self.stdout.write("3. Seeding Curriculum Subjects...")
        subjects_data = [
            ("CS301", "Design & Analysis of Algorithms", "CSE", 3, 4.0, "Divide & conquer, greedy, DP, graph algorithms, NP-completeness."),
            ("CS302", "Operating Systems", "CSE", 3, 4.0, "Process scheduling, IPC, memory virtualization, page replacement, file systems."),
            ("CS303", "Computer Networks", "CSE", 3, 3.5, "TCP/IP protocol suite, routing algorithms, congestion control, network security."),
            ("CS304", "Database Management Systems", "CSE", 3, 4.0, "Relational algebra, SQL, normalization (1NF-BCNF), indexing, ACID transactions."),
            ("EC201", "Signals and Linear Systems", "ECE", 3, 4.0, "Continuous and discrete time signals, Fourier transform, z-transform."),
        ]
        subject_map = {}
        for code, title, branch, sem, creds, syllabus in subjects_data:
            s, _ = Subject.objects.get_or_create(
                code=code,
                defaults={
                    "title": title,
                    "branch": branch,
                    "semester": sem,
                    "credits": creds,
                    "syllabus_summary": syllabus,
                }
            )
            # Assign teachers
            if code in ["CS301", "CS302"]:
                s.assigned_teachers.add(primary_teacher)
            if code in ["CS303", "CS304"]:
                s.assigned_teachers.add(secondary_teacher)
            subject_map[code] = s

        # =====================================================================
        # 4. STUDENTS & 4-SUBJECT ENROLLMENTS
        # =====================================================================
        self.stdout.write("4. Seeding Demo Students & Verified Enrollments...")
        students_data = [
            {
                "username": "student_rahul",
                "email": "rahul.sharma@edubridge.edu",
                "full_name": "Rahul Sharma",
                "public_id": "S1001",
                "branch": "CSE",
                "semester": 3,
                "is_active": True,
                "subjects": ["CS301", "CS302", "CS303", "CS304"],
            },
            {
                "username": "student_priya",
                "email": "priya.patel@edubridge.edu",
                "full_name": "Priya Patel",
                "public_id": "S1002",
                "branch": "CSE",
                "semester": 3,
                "is_active": True,
                "subjects": ["CS301", "CS302", "CS303", "CS304"],
            },
            {
                "username": "student_amit",
                "email": "amit.kumar@edubridge.edu",
                "full_name": "Amit Kumar",
                "public_id": "S1003",
                "branch": "ECE",
                "semester": 3,
                "is_active": True,
                "subjects": ["EC201", "CS301"],
            },
            {
                "username": "student_ananya",
                "email": "ananya.sen@edubridge.edu",
                "full_name": "Ananya Sen",
                "public_id": "S1004",
                "branch": "CSE",
                "semester": 3,
                "is_active": True,
                "subjects": ["CS301", "CS302", "CS303", "CS304"],
            },
            {
                "username": "student_suspended",
                "email": "suspended.demo@edubridge.edu",
                "full_name": "Vikram Singh (Suspended Demo)",
                "public_id": "S1009",
                "branch": "CSE",
                "semester": 3,
                "is_active": False,  # Specifically suspended for Admin testing
                "subjects": ["CS301", "CS302"],
            },
        ]

        created_students = {}
        for s_info in students_data:
            user = User.objects.filter(public_id=s_info["public_id"]).first()
            if not user:
                user = User.objects.filter(username=s_info["username"]).first()
            if not user:
                user = User(
                    username=s_info["username"],
                    public_id=s_info["public_id"],
                )
            user.full_name = s_info["full_name"]
            user.email = s_info["email"]
            user.role = Role.STUDENT.value
            user.is_active = s_info["is_active"]
            user.public_id = s_info["public_id"]
            user.set_password("Demo@12345")
            user.save()

            sp, _ = StudentProfile.objects.get_or_create(
                user=user,
                defaults={
                    "branch": s_info["branch"],
                    "semester": s_info["semester"],
                    "academic_details": f"Roll: {s_info['public_id']}. B.Tech Engineering cohort.",
                }
            )

            # Explicitly enroll into the 4 subjects
            for sub_code in s_info["subjects"]:
                if sub_code in subject_map:
                    user.enrolled_subjects.add(subject_map[sub_code])

            created_students[s_info["username"]] = user

        primary_student = created_students["student_rahul"]

        # =====================================================================
        # 5. ASSESSMENTS & REALISTIC ATTEMPTS
        # =====================================================================
        self.stdout.write("5. Seeding Assessments & Evaluated Attempts...")
        # Assessment 1: CS301 Daily MCQ
        ass1_mcqs = [
            {"id": i, "question": f"Algorithm Question {i}: Time complexity of finding connected components with DFS?",
             "options": ["O(V)", "O(V + E)", "O(V * E)", "O(E log V)"], "correct": "B", "marks": 2}
            for i in range(1, 11)
        ]
        ass1, _ = Assessment.objects.get_or_create(
            title="Daily Practice 05: Graph Traversal & Topological Sort",
            assessment_type=Assessment.AssessmentType.DAILY_ASSIGNMENT,
            branch="CSE",
            semester=3,
            defaults={
                "subject": subject_map["CS301"],
                "created_by": primary_teacher,
                "description": "Daily diagnostic testing DFS/BFS classification, DAG cycle detection, and topological ordering.",
                "duration_minutes": 20,
                "total_marks": 20,
                "deadline": now + timedelta(days=2),
                "questions_data": ass1_mcqs,
                "coding_problems_data": [],
                "status": Assessment.Status.PUBLISHED,
            }
        )

        # Assessment 2: CS302 Weekly Test
        ass2_mcqs = [
            {"id": i, "question": f"OS Question {i}: Which paging replacement algorithm suffers from Belady's Anomaly?",
             "options": ["LRU", "FIFO", "Optimal", "Clock Algorithm"], "correct": "B", "marks": 3}
            for i in range(1, 26)
        ]
        ass2, _ = Assessment.objects.get_or_create(
            title="Weekly Benchmark 03: Virtual Memory & Page Replacement",
            assessment_type=Assessment.AssessmentType.WEEKLY_TEST,
            branch="CSE",
            semester=3,
            defaults={
                "subject": subject_map["CS302"],
                "created_by": secondary_teacher,
                "description": "Comprehensive evaluation covering virtual addressing, TLB operation, demand paging, and page fault algorithms.",
                "duration_minutes": 90,
                "total_marks": 100,
                "deadline": now + timedelta(days=5),
                "questions_data": ass2_mcqs,
                "coding_problems_data": [],
                "status": Assessment.Status.PUBLISHED,
            }
        )

        # Assessment 3: CS304 Daily MCQ
        ass3_mcqs = [
            {"id": i, "question": f"DBMS Question {i}: Which normal form guarantees lossless join and dependency preservation?",
             "options": ["1NF", "2NF", "3NF", "BCNF"], "correct": "C", "marks": 2}
            for i in range(1, 11)
        ]
        ass3, _ = Assessment.objects.get_or_create(
            title="Daily Practice 06: Functional Dependencies & Normalization",
            assessment_type=Assessment.AssessmentType.DAILY_ASSIGNMENT,
            branch="CSE",
            semester=3,
            defaults={
                "subject": subject_map["CS304"],
                "created_by": primary_teacher,
                "description": "Daily conceptual quiz on closure of attribute sets, candidate keys, and decomposition invariants.",
                "duration_minutes": 20,
                "total_marks": 20,
                "deadline": now + timedelta(days=4),
                "questions_data": ass3_mcqs,
                "coding_problems_data": [],
                "status": Assessment.Status.PUBLISHED,
            }
        )

        # Assessment 4: CS303 Networks
        ass4_mcqs = [
            {"id": i, "question": f"Networking Question {i}: In TCP Tahoe/Reno, what triggers fast retransmission?",
             "options": ["Timeout", "3 Duplicate ACKs", "RST Flag", "Window size zero"], "correct": "B", "marks": 2}
            for i in range(1, 11)
        ]
        ass4, _ = Assessment.objects.get_or_create(
            title="Daily Practice 07: TCP Congestion Control & Flow Management",
            assessment_type=Assessment.AssessmentType.DAILY_ASSIGNMENT,
            branch="CSE",
            semester=3,
            defaults={
                "subject": subject_map["CS303"],
                "created_by": secondary_teacher,
                "description": "Practice on slow start, additive increase/multiplicative decrease, and window advertisements.",
                "duration_minutes": 20,
                "total_marks": 20,
                "deadline": now + timedelta(days=6),
                "questions_data": ass4_mcqs,
                "coding_problems_data": [],
                "status": Assessment.Status.PUBLISHED,
            }
        )

        # Record realistic attempts for Rahul Sharma across all 4 subjects
        attempts_spec = [
            (ass1, primary_student, 18.0, now - timedelta(days=5)),
            (ass2, primary_student, 84.0, now - timedelta(days=3)),
            (ass3, primary_student, 16.0, now - timedelta(days=1)),
            (ass4, primary_student, 18.0, now - timedelta(hours=6)),
            # Priya Patel attempts
            (ass1, created_students["student_priya"], 16.0, now - timedelta(days=4)),
            (ass2, created_students["student_priya"], 78.0, now - timedelta(days=2)),
            # Ananya Sen attempts
            (ass1, created_students["student_ananya"], 20.0, now - timedelta(days=5)),
            (ass2, created_students["student_ananya"], 92.0, now - timedelta(days=2)),
        ]
        for a_obj, st_obj, score_val, sub_time in attempts_spec:
            AssessmentAttempt.objects.get_or_create(
                assessment=a_obj,
                student=st_obj,
                defaults={
                    "score": score_val,
                    "status": AssessmentAttempt.AttemptStatus.COMPLETED,
                    "started_at": sub_time - timedelta(minutes=18),
                    "submitted_at": sub_time,
                    "answers": {"1": "B", "2": "B", "3": "B", "4": "B", "5": "B"},
                }
            )

        # =====================================================================
        # 6. ATTENDANCE RECORDS (Past 30 Days)
        # =====================================================================
        self.stdout.write("6. Seeding Attendance Records (Present, Absent, Late, Login)...")
        # Generate 20 daily lecture records for Rahul Sharma across the 4 subjects
        for day_offset in range(25, 0, -1):
            att_date = today - timedelta(days=day_offset)
            # Pick a rotating subject
            sub_key = ["CS301", "CS302", "CS303", "CS304"][day_offset % 4]
            sub_obj = subject_map[sub_key]

            # Realistic distribution: 20 present, 2 late, 3 absent
            if day_offset in [7, 18]:
                status_val = AttendanceRecord.Status.ABSENT
                remarks = "Absent from class session"
            elif day_offset in [12]:
                status_val = AttendanceRecord.Status.LATE
                remarks = "Joined 15 minutes late"
            else:
                status_val = AttendanceRecord.Status.PRESENT
                remarks = "Verified biometric / session log"

            AttendanceRecord.objects.get_or_create(
                student=primary_student,
                subject=sub_obj,
                date=att_date,
                session_type=AttendanceRecord.SessionType.CLASS,
                defaults={
                    "session_title": f"{sub_obj.code} Lecture: {sub_obj.title}",
                    "status": status_val,
                    "recorded_by": primary_teacher,
                    "is_auto_marked": False,
                    "remarks": remarks,
                }
            )

            # Platform activity record
            AttendanceRecord.objects.get_or_create(
                student=primary_student,
                subject=None,
                date=att_date,
                session_type=AttendanceRecord.SessionType.PLATFORM_LOGIN,
                defaults={
                    "session_title": "Daily Platform Login Activity",
                    "status": AttendanceRecord.Status.PRESENT,
                    "recorded_by": primary_student,
                    "is_auto_marked": True,
                    "remarks": "Daily verified student login session",
                }
            )

        # Today's platform login for primary student
        AttendanceRecord.objects.get_or_create(
            student=primary_student,
            subject=None,
            date=today,
            session_type=AttendanceRecord.SessionType.PLATFORM_LOGIN,
            defaults={
                "session_title": "Daily Platform Login Activity",
                "status": AttendanceRecord.Status.PRESENT,
                "recorded_by": primary_student,
                "is_auto_marked": True,
                "remarks": "Daily student platform activity",
            }
        )

        # =====================================================================
        # 7. LEARNING RESOURCES WITH THUMBNAILS
        # =====================================================================
        self.stdout.write("7. Seeding Learning Resources with Topic Visuals...")
        learning_items = [
            {
                "title": "Divide & Conquer and Master Theorem Reference Handbook",
                "description": "Comprehensive reference notes with solved recurrence relations, substitution method, and recursion trees.",
                "branch": "CSE",
                "semester": 3,
                "subject": subject_map["CS301"],
                "topic": "Master Theorem",
                "resource_type": LearningResource.ResourceType.PDF,
                "external_url": "https://www.geeksforgeeks.org/master-theorem-for-subtract-and-conquer-recurrences/",
                "thumbnail_url": "https://images.unsplash.com/photo-1509228468518-180dd4864904?w=500&q=80",
            },
            {
                "title": "Operating Systems Process Synchronization & Mutex Lab Manual",
                "description": "Hands-on POSIX thread programming in C with producer-consumer, readers-writers, and dining philosophers problems.",
                "branch": "CSE",
                "semester": 3,
                "subject": subject_map["CS302"],
                "topic": "Concurrency & Mutex",
                "resource_type": LearningResource.ResourceType.LAB_MANUAL,
                "external_url": "https://os.eecs.harvard.edu/",
                "thumbnail_url": "https://images.unsplash.com/photo-1518770660439-4636190af475?w=500&q=80",
            },
            {
                "title": "Database Relational Algebra & SQL Query Optimization Guide",
                "description": "In-depth guide covering query execution plans, B+ Tree indexing, and cost-based query optimization.",
                "branch": "CSE",
                "semester": 3,
                "subject": subject_map["CS304"],
                "topic": "SQL Optimization",
                "resource_type": LearningResource.ResourceType.NOTES,
                "external_url": "https://use-the-index-luke.com/",
                "thumbnail_url": "https://images.unsplash.com/photo-1544383835-bda2bc66a55d?w=500&q=80",
            },
            {
                "title": "Computer Networks TCP/IP Protocol Analysis & Wireshark Labs",
                "description": "Step-by-step packet inspection exercises analyzing three-way handshakes, sequence numbers, and DNS lookups.",
                "branch": "CSE",
                "semester": 3,
                "subject": subject_map["CS303"],
                "topic": "Wireshark Analysis",
                "resource_type": LearningResource.ResourceType.LAB_MANUAL,
                "external_url": "https://www.wireshark.org/docs/",
                "thumbnail_url": "https://images.unsplash.com/photo-1558494949-ef010cbdcc31?w=500&q=80",
            },
        ]

        for item in learning_items:
            LearningResource.objects.update_or_create(
                title=item["title"],
                defaults={
                    **item,
                    "author": primary_teacher,
                    "status": LearningResource.Status.PUBLISHED,
                    "download_count": 142,
                }
            )

        # =====================================================================
        # 8. CODING RESOURCES (DSA PRACTICE & ONLINE COMPILERS)
        # =====================================================================
        self.stdout.write("8. Seeding Verified External Coding Resources & Compilers...")
        from dashboards.coding_service import seed_standard_coding_resources
        seed_standard_coding_resources()

        # =====================================================================
        # 9. LIVE MEETINGS & NOTIFICATIONS
        # =====================================================================
        self.stdout.write("9. Seeding Live Sessions & Platform Notifications...")
        Meeting.objects.get_or_create(
            title="Algorithm Optimization & Recurrence Relations Masterclass",
            host_teacher=primary_teacher,
            defaults={
                "description": "Live interactive whiteboard session breaking down master theorem edge cases and dynamic programming table design.",
                "branch": "CSE",
                "semester": 3,
                "subject": subject_map["CS301"],
                "scheduled_at": now + timedelta(days=1, hours=4),
                "duration_minutes": 60,
                "meeting_link": "https://meet.google.com/edu-algo-sync",
                "status": Meeting.Status.SCHEDULED,
            }
        )

        PlatformNotification.objects.get_or_create(
            recipient=primary_student,
            title="Academic Assessment Published: Graph Traversal",
            defaults={
                "message": "Prof. Sharma published Daily Practice 05: Graph Traversal & Topological Sort. Complete before deadline.",
                "notification_type": PlatformNotification.NotificationType.ASSIGNMENT,
                "is_read": False,
            }
        )
        PlatformNotification.objects.get_or_create(
            recipient=primary_student,
            title="Verified Attendance Record",
            defaults={
                "message": "Your attendance was verified for CS301 Lecture Session with 82.5% overall semester standing.",
                "notification_type": PlatformNotification.NotificationType.PLATFORM,
                "is_read": True,
            }
        )

        self.stdout.write(self.style.SUCCESS("[SUCCESS] EduBridge Demo Dataset successfully seeded!"))
        self.stdout.write(self.style.SUCCESS(
            "Demo Credentials:\n"
            "  - Student: student_rahul / Demo@12345 (S1001, CSE Sem 3, enrolled in 4 subjects)\n"
            "  - Student: student_priya / Demo@12345 (S1002, CSE Sem 3)\n"
            "  - Teacher: prof_sharma / Demo@12345 (T2001, HOD CSE)\n"
            "  - Teacher: prof_verma / Demo@12345 (T2002, Associate Prof)\n"
            "  - Suspended Student: student_suspended / Demo@12345 (S1009, for admin inspection)\n"
        ))
