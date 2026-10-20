from django.urls import path

from . import admin_views, api, student_views, teacher_views, views

urlpatterns = [
    path("", views.home, name="home"),
    
    # -------------------------------------------------------------------------
    # Student Workspace
    # -------------------------------------------------------------------------
    path("student/", student_views.student_dashboard, name="student_dashboard"),
    path("student/analytics/", student_views.student_analytics, name="student_analytics"),
    path("api/student/analytics/", student_views.student_analytics_api, name="api_student_analytics"),
    path("student/profile/", views.student_profile, name="student_profile"),
    path("student/assessment/<int:pk>/", student_views.student_assessment_view, name="student_assessment"),
    path("student/assessment/<int:pk>/autosave/", student_views.student_assessment_autosave, name="student_assessment_autosave"),
    path("student/assessment/<int:pk>/submit/", student_views.student_assessment_submit, name="student_assessment_submit"),
    path("student/results/", student_views.student_results, name="student_results"),
    path("student/attendance/", student_views.student_attendance, name="student_attendance"),
    path("student/resources/", student_views.student_resources, name="student_resources"),
    path("student/scholarships/", student_views.student_scholarships, name="student_scholarships"),
    path("student/coding/", student_views.student_coding, name="student_coding"),
    path("api/coding/run/", student_views.coding_run_api, name="api_coding_run"),
    path("api/coding/submit/", student_views.coding_submit_api, name="api_coding_submit"),
    path("student/notifications/<int:pk>/read/", student_views.student_notification_read, name="student_notification_read"),
    path("api/student/ai/", student_views.student_ai_api, name="student_ai_api"),

    # -------------------------------------------------------------------------
    # Teacher Workspace
    # -------------------------------------------------------------------------
    path("teacher/", teacher_views.teacher_dashboard, name="teacher_dashboard"),
    path("teacher/analytics/", teacher_views.teacher_analytics, name="teacher_analytics"),
    path("api/teacher/analytics/", teacher_views.teacher_analytics_api, name="api_teacher_analytics"),
    path("teacher/coding/", teacher_views.teacher_coding, name="teacher_coding"),
    path("teacher/coding/resource/save/", teacher_views.teacher_coding_resource_save, name="teacher_coding_resource_save"),
    path("teacher/coding/resource/<int:pk>/status/", teacher_views.teacher_coding_resource_toggle_status, name="teacher_coding_resource_toggle_status"),
    path("teacher/coding/resource/<int:pk>/delete/", teacher_views.teacher_coding_resource_delete, name="teacher_coding_resource_delete"),
    path("teacher/attendance/", teacher_views.teacher_attendance, name="teacher_attendance"),
    path("api/teacher/attendance/mark/", teacher_views.teacher_attendance_mark_api, name="api_teacher_attendance_mark"),
    path("api/teacher/dsa/create/", teacher_views.teacher_dsa_create_api, name="api_teacher_dsa_create"),
    path("api/teacher/coding/analytics/", teacher_views.teacher_coding_analytics_api, name="api_teacher_coding_analytics"),
    path("teacher/profile/", views.teacher_profile, name="teacher_profile"),
    path("teacher/students/", teacher_views.teacher_students, name="teacher_students"),
    path("teacher/students/<int:pk>/", teacher_views.teacher_student_detail, name="teacher_student_detail"),
    path("teacher/assessments/", teacher_views.teacher_assessments, name="teacher_assessments"),
    path("teacher/assessments/new/", teacher_views.teacher_assessment_new, name="teacher_assessment_new"),
    path("teacher/assessments/<int:pk>/edit/", teacher_views.teacher_assessment_edit, name="teacher_assessment_edit"),
    path("teacher/assessments/<int:pk>/preview/", teacher_views.teacher_assessment_preview, name="teacher_assessment_preview"),
    path("teacher/assessments/<int:pk>/delete/", teacher_views.teacher_assessment_delete, name="teacher_assessment_delete"),
    path("api/teacher/ai-generate-questions/", teacher_views.teacher_ai_generate_questions, name="teacher_ai_generate_questions"),
    path("teacher/meetings/", teacher_views.teacher_meetings, name="teacher_meetings"),
    path("teacher/meetings/new/", teacher_views.teacher_meeting_new, name="teacher_meeting_new"),
    path("teacher/resources/", teacher_views.teacher_resources, name="teacher_resources"),
    path("api/teacher/ai/", teacher_views.teacher_ai_api, name="teacher_ai_api"),

    # -------------------------------------------------------------------------
    # Administrator Console
    # -------------------------------------------------------------------------
    path("administration/", views.admin_dashboard, name="admin_dashboard"),
    path("administration/users/", views.admin_users, name="admin_users"),
    path("administration/users/new-teacher/", views.admin_teacher_new, name="admin_teacher_new"),
    path("administration/users/<int:pk>/status/", views.admin_user_status, name="admin_user_status"),
    path("administration/audit/", views.admin_audit, name="admin_audit"),
    path("administration/analytics/", admin_views.admin_analytics, name="admin_analytics"),
    path("api/admin/analytics/", admin_views.admin_analytics_api, name="api_admin_analytics"),
    path("administration/coding/", admin_views.admin_coding, name="admin_coding"),
    path("administration/coding/resource/save/", admin_views.admin_coding_resource_save, name="admin_coding_resource_save"),
    path("administration/coding/resource/<int:pk>/status/", admin_views.admin_coding_resource_toggle_status, name="admin_coding_resource_toggle_status"),
    path("administration/coding/resource/<int:pk>/delete/", admin_views.admin_coding_resource_delete, name="admin_coding_resource_delete"),
    path("administration/attendance/", admin_views.admin_attendance, name="admin_attendance"),
    path("api/admin/attendance/correct/", admin_views.admin_attendance_correct_api, name="api_admin_attendance_correct"),
    path("api/admin/coding/analytics/", admin_views.admin_coding_analytics_api, name="api_admin_coding_analytics"),
    path("administration/export/<str:report_type>/", admin_views.admin_export_csv, name="admin_export_csv"),
    path("administration/students/", admin_views.admin_students, name="admin_students"),
    path("administration/students/<int:pk>/", admin_views.admin_student_detail, name="admin_student_detail"),
    path("administration/teachers/", admin_views.admin_teachers, name="admin_teachers"),
    path("administration/teachers/<int:pk>/", admin_views.admin_teacher_detail, name="admin_teacher_detail"),
    path("administration/academic/", admin_views.admin_academic, name="admin_academic"),
    path("administration/assessments/", admin_views.admin_assessments, name="admin_assessments"),
    path("administration/resources/", admin_views.admin_resources, name="admin_resources"),
    path("administration/scholarships/", admin_views.admin_scholarships, name="admin_scholarships"),
    path("administration/meetings/", admin_views.admin_meetings, name="admin_meetings"),
    path("administration/notifications/", admin_views.admin_notifications, name="admin_notifications"),
    path("administration/settings/", admin_views.admin_settings, name="admin_settings"),
    path("administration/ai/", admin_views.admin_ai_assistant, name="admin_ai_assistant"),
    path("administration/api/ai/", admin_views.admin_ai_api, name="admin_ai_api"),

    # -------------------------------------------------------------------------
    # JSON API (Role-governed)
    # -------------------------------------------------------------------------
    path("api/me/", api.me, name="api_me"),
    path("api/student/profile/", api.student_profile, name="api_student_profile"),
    path("api/teacher/profile/", api.teacher_profile, name="api_teacher_profile"),
    path("api/admin/stats/", api.admin_stats, name="api_admin_stats"),
    path("api/admin/users/", api.admin_users, name="api_admin_users"),
    path("api/notifications/", api.notifications_list, name="api_notifications_list"),
    path("api/notifications/<int:pk>/read/", api.notification_mark_read, name="api_notification_mark_read"),
    path("api/notifications/read-all/", api.notification_mark_all_read, name="api_notification_read_all"),
    path("api/ai/chat/", api.unified_ai_chat_api, name="api_ai_chat"),
    path("api/ai/chat", api.unified_ai_chat_api),
]
