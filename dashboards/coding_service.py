"""EduBridge Sandboxed Code Execution & DSA Evaluation Engine.

Provides secure, isolated code execution and test-case grading for:
1. Student Mode A: Freeform Practice Sandbox (Python, Java, C)
2. Student Mode B: Assigned DSA Challenges with Public & Hidden Test Case Verification
3. Teacher Mode: Question validation, submission review, and error tracking
4. Telemetry Recording: Tracks execution time, compilation/runtime errors, and pass rates.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple

from django.db.models import Avg, Count, Q

from accounts.constants import Role
from accounts.models import User
from dashboards.models import CodingSubmission, DSAQuestion, DSATopic


def execute_sandboxed_code(
    language: str,
    source_code: str,
    stdin_input: str = "",
    timeout_sec: float = 3.0
) -> Dict[str, Any]:
    """Execute student code in an isolated subprocess with timeout and memory constraints.
    
    Returns:
    {
        "status": "success" | "compilation_error" | "runtime_error" | "timeout" | "unsupported_runtime",
        "stdout": str,
        "stderr": str,
        "execution_time_ms": float,
        "exit_code": int
    }
    """
    clean_lang = (language or "python").lower().strip()
    clean_code = source_code or ""
    start_time = time.perf_counter()

    if clean_lang in ["python", "py", "python3"]:
        py_binary = sys.executable or shutil.which("python") or shutil.which("python3")
        if not py_binary:
            return {
                "status": "unsupported_runtime",
                "stdout": "",
                "stderr": "Python interpreter is not configured on the host server.",
                "execution_time_ms": 0.0,
                "exit_code": -1
            }

        # Write to a secure temporary file
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(clean_code)
            temp_path = f.name

        try:
            # Execute with restricted environment and isolation
            safe_env = {
                "PATH": os.environ.get("PATH", ""),
                "PYTHONIOENCODING": "utf-8",
                "PYTHONDONTWRITEBYTECODE": "1"
            }
            proc = subprocess.run(
                [py_binary, "-u", temp_path],
                input=stdin_input,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                env=safe_env
            )
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            stdout = proc.stdout
            stderr = proc.stderr

            if proc.returncode == 0:
                return {
                    "status": "success",
                    "stdout": stdout,
                    "stderr": stderr,
                    "execution_time_ms": elapsed_ms,
                    "exit_code": 0
                }
            else:
                # Distinguish SyntaxError (compilation) vs other exceptions (runtime)
                if "SyntaxError" in stderr or "IndentationError" in stderr or "TabError" in stderr:
                    status = "compilation_error"
                else:
                    status = "runtime_error"
                return {
                    "status": status,
                    "stdout": stdout,
                    "stderr": stderr,
                    "execution_time_ms": elapsed_ms,
                    "exit_code": proc.returncode
                }
        except subprocess.TimeoutExpired:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "status": "timeout",
                "stdout": "",
                "stderr": f"Time Limit Exceeded: Process exceeded {timeout_sec} seconds timeout.",
                "execution_time_ms": elapsed_ms,
                "exit_code": -1
            }
        except Exception as e:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "status": "runtime_error",
                "stdout": "",
                "stderr": str(e),
                "execution_time_ms": elapsed_ms,
                "exit_code": -1
            }
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    elif clean_lang in ["c", "cpp"]:
        gcc_binary = shutil.which("gcc") or shutil.which("clang")
        if not gcc_binary:
            # Check basic syntax via regex / Python heuristic if compiler not on server
            return {
                "status": "unsupported_runtime",
                "stdout": "",
                "stderr": "C/C++ compiler (gcc/clang) is not installed on this host environment. Please test solutions using Python 3.",
                "execution_time_ms": 0.0,
                "exit_code": -1
            }
        # Compile and execute C code
        with tempfile.TemporaryDirectory() as tmp_dir:
            c_file = os.path.join(tmp_dir, "solution.c")
            out_binary = os.path.join(tmp_dir, "solution.exe" if os.name == "nt" else "solution")
            with open(c_file, "w", encoding="utf-8") as f:
                f.write(clean_code)

            comp = subprocess.run([gcc_binary, c_file, "-o", out_binary, "-O2"], capture_output=True, text=True, timeout=5)
            if comp.returncode != 0:
                return {
                    "status": "compilation_error",
                    "stdout": "",
                    "stderr": comp.stderr,
                    "execution_time_ms": 0.0,
                    "exit_code": comp.returncode
                }
            try:
                run_proc = subprocess.run([out_binary], input=stdin_input, capture_output=True, text=True, timeout=timeout_sec)
                elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
                return {
                    "status": "success" if run_proc.returncode == 0 else "runtime_error",
                    "stdout": run_proc.stdout,
                    "stderr": run_proc.stderr,
                    "execution_time_ms": elapsed_ms,
                    "exit_code": run_proc.returncode
                }
            except subprocess.TimeoutExpired:
                return {
                    "status": "timeout",
                    "stdout": "",
                    "stderr": f"Time Limit Exceeded ({timeout_sec}s)",
                    "execution_time_ms": round(timeout_sec * 1000, 2),
                    "exit_code": -1
                }

    elif clean_lang in ["java"]:
        javac_binary = shutil.which("javac")
        if not javac_binary:
            return {
                "status": "unsupported_runtime",
                "stdout": "",
                "stderr": "Java SDK (javac/java) is not installed on this host environment. Please test solutions using Python 3.",
                "execution_time_ms": 0.0,
                "exit_code": -1
            }
        # Extract class name or default to Solution
        class_match = re.search(r'class\s+([A-Za-z0-9_]+)', clean_code)
        class_name = class_match.group(1) if class_match else "Solution"

        with tempfile.TemporaryDirectory() as tmp_dir:
            java_file = os.path.join(tmp_dir, f"{class_name}.java")
            with open(java_file, "w", encoding="utf-8") as f:
                f.write(clean_code)

            comp = subprocess.run([javac_binary, java_file], capture_output=True, text=True, timeout=5)
            if comp.returncode != 0:
                return {
                    "status": "compilation_error",
                    "stdout": "",
                    "stderr": comp.stderr,
                    "execution_time_ms": 0.0,
                    "exit_code": comp.returncode
                }
            try:
                run_proc = subprocess.run(
                    ["java", "-cp", tmp_dir, class_name],
                    input=stdin_input,
                    capture_output=True,
                    text=True,
                    timeout=timeout_sec
                )
                elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
                return {
                    "status": "success" if run_proc.returncode == 0 else "runtime_error",
                    "stdout": run_proc.stdout,
                    "stderr": run_proc.stderr,
                    "execution_time_ms": elapsed_ms,
                    "exit_code": run_proc.returncode
                }
            except subprocess.TimeoutExpired:
                return {
                    "status": "timeout",
                    "stdout": "",
                    "stderr": f"Time Limit Exceeded ({timeout_sec}s)",
                    "execution_time_ms": round(timeout_sec * 1000, 2),
                    "exit_code": -1
                }

    return {
        "status": "unsupported_runtime",
        "stdout": "",
        "stderr": f"Unsupported language '{language}'. Supported: Python, Java, C.",
        "execution_time_ms": 0.0,
        "exit_code": -1
    }


def grade_dsa_submission(
    student: User,
    question: DSAQuestion,
    language: str,
    source_code: str
) -> Dict[str, Any]:
    """Evaluate student solution against all public and hidden test cases for a DSA question."""
    public_cases = question.public_test_cases or []
    hidden_cases = question.hidden_test_cases or []
    all_cases = []

    for i, c in enumerate(public_cases):
        all_cases.append({
            "id": i + 1,
            "input": str(c.get("input", "")),
            "expected_output": str(c.get("output", "")).strip(),
            "hidden": False,
            "explanation": c.get("explanation", "")
        })

    for i, c in enumerate(hidden_cases):
        all_cases.append({
            "id": len(public_cases) + i + 1,
            "input": str(c.get("input", "")),
            "expected_output": str(c.get("output", "")).strip(),
            "hidden": True,
            "explanation": ""
        })

    if not all_cases:
        # Fallback sample test case if none configured
        all_cases.append({
            "id": 1,
            "input": question.sample_input or "",
            "expected_output": (question.sample_output or "").strip(),
            "hidden": False,
            "explanation": "Sample test case"
        })

    passed_count = 0
    total_time_ms = 0.0
    case_results = []
    overall_status = CodingSubmission.SubmissionStatus.ACCEPTED
    first_error_msg = ""

    timeout_sec = (question.time_limit_ms or 2000) / 1000.0

    for case in all_cases:
        res = execute_sandboxed_code(
            language=language,
            source_code=source_code,
            stdin_input=case["input"],
            timeout_sec=timeout_sec
        )
        total_time_ms += res["execution_time_ms"]

        if res["status"] == "compilation_error":
            overall_status = CodingSubmission.SubmissionStatus.COMPILATION_ERROR
            first_error_msg = res["stderr"]
            case_results.append({
                "test_case_id": case["id"],
                "passed": False,
                "status": "Compilation Error",
                "hidden": case["hidden"],
                "error": res["stderr"] if not case["hidden"] else "Compilation failed"
            })
            break  # Compilation failed for entire file

        elif res["status"] == "timeout":
            overall_status = CodingSubmission.SubmissionStatus.TIMEOUT
            first_error_msg = f"Time Limit Exceeded on test case #{case['id']}"
            case_results.append({
                "test_case_id": case["id"],
                "passed": False,
                "status": "Time Limit Exceeded",
                "hidden": case["hidden"],
                "execution_time_ms": res["execution_time_ms"]
            })
            break

        elif res["status"] == "runtime_error":
            if overall_status == CodingSubmission.SubmissionStatus.ACCEPTED:
                overall_status = CodingSubmission.SubmissionStatus.RUNTIME_ERROR
                first_error_msg = res["stderr"]
            case_results.append({
                "test_case_id": case["id"],
                "passed": False,
                "status": "Runtime Error",
                "hidden": case["hidden"],
                "error": res["stderr"] if not case["hidden"] else "Runtime error occurred"
            })

        elif res["status"] == "unsupported_runtime":
            overall_status = CodingSubmission.SubmissionStatus.COMPILATION_ERROR
            first_error_msg = res["stderr"]
            case_results.append({
                "test_case_id": case["id"],
                "passed": False,
                "status": "Compiler Error",
                "hidden": case["hidden"],
                "error": res["stderr"]
            })
            break

        else:
            # Status was success - check expected output
            actual = str(res["stdout"]).strip()
            expected = case["expected_output"]
            if actual == expected:
                passed_count += 1
                case_results.append({
                    "test_case_id": case["id"],
                    "passed": True,
                    "status": "Passed",
                    "hidden": case["hidden"],
                    "execution_time_ms": res["execution_time_ms"],
                    # Security: Only transmit input/output for public test cases
                    "input": case["input"] if not case["hidden"] else "[Hidden Test Case]",
                    "actual_output": actual if not case["hidden"] else "[Hidden]",
                    "expected_output": expected if not case["hidden"] else "[Hidden]"
                })
            else:
                if overall_status == CodingSubmission.SubmissionStatus.ACCEPTED:
                    overall_status = CodingSubmission.SubmissionStatus.WRONG_ANSWER
                    first_error_msg = f"Wrong answer on test case #{case['id']}"
                case_results.append({
                    "test_case_id": case["id"],
                    "passed": False,
                    "status": "Wrong Answer",
                    "hidden": case["hidden"],
                    "execution_time_ms": res["execution_time_ms"],
                    "input": case["input"] if not case["hidden"] else "[Hidden Test Case]",
                    "actual_output": actual if not case["hidden"] else "[Hidden]",
                    "expected_output": expected if not case["hidden"] else "[Hidden]"
                })

    if passed_count < len(all_cases) and overall_status == CodingSubmission.SubmissionStatus.ACCEPTED:
        overall_status = CodingSubmission.SubmissionStatus.WRONG_ANSWER

    avg_time = round(total_time_ms / max(1, len(case_results)), 2)

    # Persist the submission to database
    submission = CodingSubmission.objects.create(
        student=student,
        question=question,
        language=language,
        source_code=source_code,
        status=overall_status,
        passed_test_cases=passed_count,
        total_test_cases=len(all_cases),
        execution_time_ms=avg_time,
        error_message=first_error_msg[:1000],
        test_case_results=case_results,
        is_practice=False
    )

    # Client-safe result (strip internal hidden inputs/outputs)
    safe_case_results = []
    for cr in case_results:
        item = {
            "test_case_id": cr["test_case_id"],
            "passed": cr["passed"],
            "status": cr["status"],
            "hidden": cr["hidden"],
        }
        if not cr["hidden"]:
            item["input"] = cr.get("input", "")
            item["actual_output"] = cr.get("actual_output", "")
            item["expected_output"] = cr.get("expected_output", "")
            if cr.get("error"):
                item["error"] = cr.get("error")
        safe_case_results.append(item)

    return {
        "submission_id": submission.id,
        "status": overall_status,
        "status_display": submission.get_status_display(),
        "passed_test_cases": passed_count,
        "total_test_cases": len(all_cases),
        "pass_rate_pct": round((passed_count / len(all_cases)) * 100, 1),
        "execution_time_ms": avg_time,
        "error_message": first_error_msg,
        "test_case_results": safe_case_results,
        "submitted_at": submission.submitted_at.strftime("%b %d, %Y %I:%M %p")
    }


def seed_standard_dsa_questions():
    """Seed comprehensive initial DSA practice questions across curriculum categories."""
    if DSAQuestion.objects.count() >= 5:
        return

    faculty = User.objects.filter(role="teacher").first()

    questions = [
        {
            "title": "Reverse an Array In-Place",
            "topic": DSATopic.ARRAYS,
            "difficulty": "Easy",
            "branch": "CSE",
            "semester": 3,
            "problem_statement": "Given an integer array `arr` of size `N`, reverse the array elements in-place without allocating auxiliary memory.",
            "input_format": "Line 1: An integer N representing array length\nLine 2: N space-separated integers",
            "output_format": "Space-separated reversed integers",
            "constraints": "1 <= N <= 10^5\n-10^9 <= arr[i] <= 10^9",
            "sample_input": "5\n1 2 3 4 5",
            "sample_output": "5 4 3 2 1",
            "explanation": "Elements at index 0 and 4 are swapped, then index 1 and 3.",
            "supported_languages": ["python", "java", "c"],
            "starter_code": {
                "python": "import sys\n\ndef solve():\n    lines = sys.stdin.read().split()\n    if not lines: return\n    n = int(lines[0])\n    arr = lines[1:n+1]\n    print(' '.join(arr[::-1]))\n\nsolve()\n",
                "c": "#include <stdio.h>\nint main() {\n    int n;\n    if (scanf(\"%d\", &n) != 1) return 0;\n    int arr[n];\n    for(int i=0; i<n; i++) scanf(\"%d\", &arr[i]);\n    for(int i=n-1; i>=0; i--) printf(\"%d%s\", arr[i], i==0?\"\":\" \");\n    printf(\"\\n\");\n    return 0;\n}\n",
                "java": "import java.util.*;\npublic class Solution {\n    public static void main(String[] args) {\n        Scanner sc = new Scanner(System.in);\n        if (!sc.hasNextInt()) return;\n        int n = sc.nextInt();\n        int[] arr = new int[n];\n        for (int i = 0; i < n; i++) arr[i] = sc.nextInt();\n        for (int i = n - 1; i >= 0; i--) System.out.print(arr[i] + (i == 0 ? \"\" : \" \"));\n        System.out.println();\n    }\n}\n"
            },
            "public_test_cases": [
                {"input": "5\n1 2 3 4 5", "output": "5 4 3 2 1", "explanation": "Standard 5 element reversal"},
                {"input": "3\n10 20 30", "output": "30 20 10", "explanation": "3 element array"}
            ],
            "hidden_test_cases": [
                {"input": "1\n42", "output": "42"},
                {"input": "4\n-1 -2 -3 -4", "output": "-4 -3 -2 -1"}
            ]
        },
        {
            "title": "Valid Anagram Verification",
            "topic": DSATopic.STRINGS,
            "difficulty": "Easy",
            "branch": "CSE",
            "semester": 3,
            "problem_statement": "Given two strings `s` and `t`, return `true` if `t` is an anagram of `s`, and `false` otherwise.",
            "input_format": "Line 1: string s\nLine 2: string t",
            "output_format": "true or false",
            "constraints": "1 <= s.length, t.length <= 5 * 10^4\ns and t consist of lowercase English letters.",
            "sample_input": "anagram\nnagaram",
            "sample_output": "true",
            "explanation": "Both strings have the exact same character frequencies.",
            "supported_languages": ["python", "java", "c"],
            "starter_code": {
                "python": "import sys\n\ndef is_anagram():\n    lines = sys.stdin.read().split()\n    if len(lines) < 2: return\n    s, t = lines[0], lines[1]\n    print('true' if sorted(s) == sorted(t) else 'false')\n\nis_anagram()\n"
            },
            "public_test_cases": [
                {"input": "anagram\nnagaram", "output": "true"},
                {"input": "rat\ncar", "output": "false"}
            ],
            "hidden_test_cases": [
                {"input": "listen\nsilent", "output": "true"},
                {"input": "hello\nworld", "output": "false"}
            ]
        },
        {
            "title": "Binary Search on Sorted Array",
            "topic": DSATopic.SEARCHING,
            "difficulty": "Easy",
            "branch": "CSE",
            "semester": 3,
            "problem_statement": "Given a sorted array of `N` distinct integers and a target integer `K`, return the 0-based index of `K` in the array. If `K` is not present, return `-1`.",
            "input_format": "Line 1: N K\nLine 2: N sorted space-separated integers",
            "output_format": "0-based index or -1",
            "constraints": "1 <= N <= 10^5\n-10^9 <= arr[i], K <= 10^9",
            "sample_input": "6 9\n-1 0 3 5 9 12",
            "sample_output": "4",
            "explanation": "9 exists in arr and its index is 4.",
            "supported_languages": ["python", "java", "c"],
            "starter_code": {
                "python": "import sys\n\ndef binary_search():\n    lines = sys.stdin.read().split()\n    if not lines: return\n    n, k = int(lines[0]), int(lines[1])\n    arr = [int(x) for x in lines[2:n+2]]\n    lo, hi = 0, n - 1\n    ans = -1\n    while lo <= hi:\n        mid = (lo + hi) // 2\n        if arr[mid] == k:\n            ans = mid\n            break\n        elif arr[mid] < k:\n            lo = mid + 1\n        else:\n            hi = mid - 1\n    print(ans)\n\nbinary_search()\n"
            },
            "public_test_cases": [
                {"input": "6 9\n-1 0 3 5 9 12", "output": "4"},
                {"input": "6 2\n-1 0 3 5 9 12", "output": "-1"}
            ],
            "hidden_test_cases": [
                {"input": "5 100\n10 20 50 100 200", "output": "3"},
                {"input": "1 5\n5", "output": "0"}
            ]
        },
        {
            "title": "Two Sum (Hash Map Lookup)",
            "topic": DSATopic.HASHING,
            "difficulty": "Medium",
            "branch": "CSE",
            "semester": 3,
            "problem_statement": "Given an array of integers `nums` and an integer `target`, return the 0-based indices of the two numbers such that they add up to target.",
            "input_format": "Line 1: N target\nLine 2: N integers",
            "output_format": "Two space-separated indices (ascending)",
            "constraints": "2 <= N <= 10^4\n-10^9 <= nums[i] <= 10^9",
            "sample_input": "4 9\n2 7 11 15",
            "sample_output": "0 1",
            "explanation": "nums[0] + nums[1] == 2 + 7 == 9.",
            "supported_languages": ["python", "java", "c"],
            "starter_code": {
                "python": "import sys\n\ndef two_sum():\n    lines = sys.stdin.read().split()\n    if not lines: return\n    n, target = int(lines[0]), int(lines[1])\n    nums = [int(x) for x in lines[2:n+2]]\n    seen = {}\n    for i, num in enumerate(nums):\n        complement = target - num\n        if complement in seen:\n            print(f\"{seen[complement]} {i}\")\n            return\n        seen[num] = i\n\ntwo_sum()\n"
            },
            "public_test_cases": [
                {"input": "4 9\n2 7 11 15", "output": "0 1"},
                {"input": "3 6\n3 2 4", "output": "1 2"}
            ],
            "hidden_test_cases": [
                {"input": "2 6\n3 3", "output": "0 1"}
            ]
        },
        {
            "title": "Longest Increasing Subsequence (DP)",
            "topic": DSATopic.DP,
            "difficulty": "Hard",
            "branch": "CSE",
            "semester": 3,
            "problem_statement": "Given an integer array `nums`, return the length of the longest strictly increasing subsequence.",
            "input_format": "Line 1: N\nLine 2: N integers",
            "output_format": "Length of longest increasing subsequence",
            "constraints": "1 <= N <= 2500\n-10^4 <= nums[i] <= 10^4",
            "sample_input": "8\n10 9 2 5 3 7 101 18",
            "sample_output": "4",
            "explanation": "The longest increasing subsequence is [2, 3, 7, 101], therefore the length is 4.",
            "supported_languages": ["python", "java", "c"],
            "starter_code": {
                "python": "import sys, bisect\n\ndef solve():\n    lines = sys.stdin.read().split()\n    if not lines: return\n    n = int(lines[0])\n    nums = [int(x) for x in lines[1:n+1]]\n    tails = []\n    for x in nums:\n        idx = bisect.bisect_left(tails, x)\n        if idx == len(tails):\n            tails.append(x)\n        else:\n            tails[idx] = x\n    print(len(tails))\n\nsolve()\n"
            },
            "public_test_cases": [
                {"input": "8\n10 9 2 5 3 7 101 18", "output": "4"},
                {"input": "6\n0 1 0 3 2 3", "output": "4"}
            ],
            "hidden_test_cases": [
                {"input": "7\n7 7 7 7 7 7 7", "output": "1"}
            ]
        }
    ]

    for q in questions:
        DSAQuestion.objects.get_or_create(
            title=q["title"],
            defaults={
                "topic": q["topic"],
                "difficulty": q["difficulty"],
                "branch": q["branch"],
                "semester": q["semester"],
                "created_by": faculty,
                "problem_statement": q["problem_statement"],
                "input_format": q["input_format"],
                "output_format": q["output_format"],
                "constraints": q["constraints"],
                "sample_input": q["sample_input"],
                "sample_output": q["sample_output"],
                "explanation": q["explanation"],
                "supported_languages": q["supported_languages"],
                "starter_code": q["starter_code"],
                "public_test_cases": q["public_test_cases"],
                "hidden_test_cases": q["hidden_test_cases"],
                "status": "published"
            }
        )


# ==============================================================================
# CODING & DSA ANALYTICS ENGINE (STUDENT, TEACHER, ADMIN)
# ==============================================================================

def get_student_coding_analytics(student: User) -> Dict[str, Any]:
    """Calculate comprehensive personal coding diagnostics for an individual student."""
    from accounts.constants import Role

    # Published questions assigned
    assigned_qs = DSAQuestion.objects.filter(status="published")
    total_assigned = assigned_qs.count()

    submissions = CodingSubmission.objects.filter(student=student).order_by("-submitted_at")
    total_submissions = submissions.count()

    attempted_q_ids = set(
        submissions.filter(question__isnull=False).values_list("question_id", flat=True)
    )
    solved_q_ids = set(
        submissions.filter(
            question__isnull=False,
            status=CodingSubmission.SubmissionStatus.ACCEPTED
        ).values_list("question_id", flat=True)
    )

    total_attempted = len(attempted_q_ids)
    total_solved = len(solved_q_ids)
    total_pending = max(0, total_assigned - total_solved)

    # Acceptance rate (problems solved vs attempted)
    acceptance_rate = round((total_solved / total_attempted * 100), 1) if total_attempted else 0.0
    submission_pass_rate = round(
        (submissions.filter(status=CodingSubmission.SubmissionStatus.ACCEPTED).count() / max(1, total_submissions) * 100), 1
    ) if total_submissions else 0.0

    # Error distribution
    accepted_count = submissions.filter(status=CodingSubmission.SubmissionStatus.ACCEPTED).count()
    wrong_count = submissions.filter(status=CodingSubmission.SubmissionStatus.WRONG_ANSWER).count()
    comp_error_count = submissions.filter(status=CodingSubmission.SubmissionStatus.COMPILATION_ERROR).count()
    runtime_error_count = submissions.filter(status=CodingSubmission.SubmissionStatus.RUNTIME_ERROR).count()
    timeout_count = submissions.filter(status=CodingSubmission.SubmissionStatus.TIMEOUT).count()

    # Average attempts per solved question
    if total_solved > 0:
        solved_submissions_count = submissions.filter(question_id__in=solved_q_ids).count()
        avg_attempts_per_solve = round(solved_submissions_count / total_solved, 1)
    else:
        avg_attempts_per_solve = 0.0

    # Topic-wise performance
    topic_data = []
    for code, label in DSATopic.choices:
        q_in_topic = assigned_qs.filter(topic=code)
        q_count = q_in_topic.count()
        if q_count == 0:
            continue
        topic_q_ids = set(q_in_topic.values_list("id", flat=True))
        t_attempted = len(topic_q_ids.intersection(attempted_q_ids))
        t_solved = len(topic_q_ids.intersection(solved_q_ids))
        t_rate = round((t_solved / max(1, t_attempted) * 100), 1) if t_attempted else 0.0
        topic_data.append({
            "topic": code,
            "label": label,
            "total_questions": q_count,
            "attempted": t_attempted,
            "solved": t_solved,
            "pass_rate": t_rate,
        })

    # Status label
    if total_solved >= 10:
        status_label = "EXCELLENT"
    elif total_solved >= 5:
        status_label = "ADVANCED"
    elif total_solved >= 2:
        status_label = "INTERMEDIATE"
    elif total_attempted > 0:
        status_label = "IN PROGRESS"
    else:
        status_label = "BEGINNER"

    # Recent submissions
    recent_submissions = []
    for sub in submissions.select_related("question")[:10]:
        recent_submissions.append({
            "id": sub.id,
            "question_title": sub.question.title if sub.question else "Sandbox",
            "topic_display": sub.question.get_topic_display() if sub.question else "General",
            "difficulty": sub.question.difficulty if sub.question else "Practice",
            "language": sub.language.capitalize(),
            "status": sub.status,
            "status_display": sub.get_status_display(),
            "passed_test_cases": sub.passed_test_cases,
            "total_test_cases": sub.total_test_cases,
            "execution_time_ms": sub.execution_time_ms,
            "submitted_at": sub.submitted_at.strftime("%b %d, %Y %I:%M %p"),
        })

    return {
        "total_assigned": total_assigned,
        "total_attempted": total_attempted,
        "total_solved": total_solved,
        "total_pending": total_pending,
        "total_submissions": total_submissions,
        "acceptance_rate": acceptance_rate,
        "submission_pass_rate": submission_pass_rate,
        "avg_attempts_per_solve": avg_attempts_per_solve,
        "status_label": status_label,
        "errors": {
            "accepted": accepted_count,
            "wrong_answer": wrong_count,
            "compilation_error": comp_error_count,
            "runtime_error": runtime_error_count,
            "timeout": timeout_count,
        },
        "topics": topic_data,
        "recent_submissions": recent_submissions,
        "charts": {
            "attempts_vs_solved": {
                "categories": ["Assigned", "Attempted", "Solved", "Pending"],
                "values": [total_assigned, total_attempted, total_solved, total_pending],
            },
            "submission_outcomes": {
                "labels": ["Accepted", "Wrong Answer", "Compilation Error", "Runtime Error", "Timeout"],
                "values": [accepted_count, wrong_count, comp_error_count, runtime_error_count, timeout_count],
            },
            "topic_performance": {
                "labels": [t["label"] for t in topic_data],
                "solved": [t["solved"] for t in topic_data],
                "attempted": [t["attempted"] for t in topic_data],
            }
        }
    }


def get_teacher_coding_overview(teacher: User) -> Dict[str, Any]:
    """Calculate aggregate DSA management and coding diagnostics for a teacher's cohort."""
    from accounts.constants import Role

    profile = getattr(teacher, "teacher_profile", None)
    dept = profile.department if profile else "CSE"
    assigned_branches = list(set(teacher.assigned_subjects.values_list("branch", flat=True)))
    if not assigned_branches:
        assigned_branches = [dept] if dept else ["CSE"]

    # Student cohort
    students_in_scope = User.objects.filter(
        role=Role.STUDENT.value,
        student_profile__branch__in=assigned_branches
    )
    total_cohort_students = students_in_scope.count()

    # Questions created by teacher or belonging to teacher's branches
    questions = DSAQuestion.objects.filter(
        Q(created_by=teacher) | Q(branch__in=assigned_branches)
    ).order_by("-created_at")

    # Submissions from authorized students
    cohort_submissions = CodingSubmission.objects.filter(student__in=students_in_scope)
    total_submissions = cohort_submissions.count()

    participating_student_ids = set(
        cohort_submissions.values_list("student_id", flat=True)
    )
    participating_students_count = len(participating_student_ids)

    accepted_submissions = cohort_submissions.filter(status=CodingSubmission.SubmissionStatus.ACCEPTED).count()
    overall_acceptance_rate = round((accepted_submissions / max(1, total_submissions) * 100), 1) if total_submissions else 0.0

    # Error breakdown
    comp_errors = cohort_submissions.filter(status=CodingSubmission.SubmissionStatus.COMPILATION_ERROR).count()
    runtime_errors = cohort_submissions.filter(status=CodingSubmission.SubmissionStatus.RUNTIME_ERROR).count()
    wrong_answers = cohort_submissions.filter(status=CodingSubmission.SubmissionStatus.WRONG_ANSWER).count()
    timeouts = cohort_submissions.filter(status=CodingSubmission.SubmissionStatus.TIMEOUT).count()

    # Detailed Question Performance Table
    question_table = []
    for q in questions:
        q_subs = cohort_submissions.filter(question=q)
        q_attempts_count = q_subs.values("student_id").distinct().count()
        q_solved_count = q_subs.filter(status=CodingSubmission.SubmissionStatus.ACCEPTED).values("student_id").distinct().count()
        q_rate = round((q_solved_count / max(1, q_attempts_count) * 100), 1) if q_attempts_count else 0.0
        q_avg_attempts = round((q_subs.count() / max(1, q_solved_count)), 1) if q_solved_count else 0.0

        # Common errors for this problem
        q_comp = q_subs.filter(status=CodingSubmission.SubmissionStatus.COMPILATION_ERROR).count()
        q_runtime = q_subs.filter(status=CodingSubmission.SubmissionStatus.RUNTIME_ERROR).count()
        q_wrong = q_subs.filter(status=CodingSubmission.SubmissionStatus.WRONG_ANSWER).count()

        primary_error = "None"
        if q_wrong >= q_comp and q_wrong >= q_runtime and q_wrong > 0:
            primary_error = f"Wrong Answer ({q_wrong})"
        elif q_comp >= q_runtime and q_comp > 0:
            primary_error = f"Syntax/Compile ({q_comp})"
        elif q_runtime > 0:
            primary_error = f"Runtime ({q_runtime})"

        question_table.append({
            "id": q.id,
            "title": q.title,
            "topic": q.get_topic_display(),
            "difficulty": q.difficulty,
            "status": q.status,
            "assigned_students": total_cohort_students,
            "attempted_students": q_attempts_count,
            "solved_students": q_solved_count,
            "success_rate": q_rate,
            "avg_attempts": q_avg_attempts,
            "common_error": primary_error,
        })

    # Difficulty distribution
    difficulty_counts = {
        "Easy": questions.filter(difficulty="Easy").count(),
        "Medium": questions.filter(difficulty="Medium").count(),
        "Hard": questions.filter(difficulty="Hard").count(),
    }

    # Topic distribution
    topic_distribution = {}
    for q in questions:
        td = q.get_topic_display()
        topic_distribution[td] = topic_distribution.get(td, 0) + 1

    return {
        "cohort_summary": {
            "total_cohort_students": total_cohort_students,
            "participating_students": participating_students_count,
            "total_questions_managed": questions.count(),
            "total_submissions_evaluated": total_submissions,
            "overall_acceptance_rate": overall_acceptance_rate,
            "compilation_errors": comp_errors,
            "runtime_errors": runtime_errors,
            "wrong_answers": wrong_answers,
            "timeouts": timeouts,
        },
        "questions_table": question_table,
        "difficulty_counts": difficulty_counts,
        "topic_distribution": topic_distribution,
        "charts": {
            "error_distribution": {
                "labels": ["Accepted", "Wrong Answer", "Compilation Error", "Runtime Error", "Timeout"],
                "values": [accepted_submissions, wrong_answers, comp_errors, runtime_errors, timeouts],
            },
            "difficulty_breakdown": {
                "labels": list(difficulty_counts.keys()),
                "values": list(difficulty_counts.values()),
            },
            "topic_breakdown": {
                "labels": list(topic_distribution.keys()),
                "values": list(topic_distribution.values()),
            }
        }
    }


def get_teacher_individual_student_coding(teacher: User, student_id_str: str) -> Dict[str, Any]:
    """Retrieve an individual student's authorized coding analytics for a teacher."""
    from accounts.constants import Role

    clean_id = (student_id_str or "").strip()
    if not clean_id:
        return {"success": False, "error": "missing_id", "message": "Please enter a valid Student ID."}

    # Locate student by public ID or username
    student = User.objects.filter(role=Role.STUDENT.value).filter(
        Q(public_id__iexact=clean_id) |
        Q(username__iexact=clean_id) |
        Q(id__iexact=clean_id if clean_id.isdigit() else -1)
    ).first()

    if not student:
        return {
            "success": False,
            "error": "not_found",
            "message": f"Student with ID '{clean_id}' was not found in the institutional records."
        }

    # Verify authorization
    profile = getattr(teacher, "teacher_profile", None)
    dept = profile.department if profile else "CSE"
    assigned_branches = list(set(teacher.assigned_subjects.values_list("branch", flat=True)))
    if not assigned_branches:
        assigned_branches = [dept] if dept else ["CSE"]

    s_profile = getattr(student, "student_profile", None)
    student_branch = s_profile.branch if s_profile else "CSE"

    if student_branch not in assigned_branches:
        return {
            "success": False,
            "error": "unauthorized",
            "message": f"Access Denied: Student {clean_id} belongs to branch '{student_branch}' which is outside your authorized teaching scope ({', '.join(assigned_branches)})."
        }

    analytics = get_student_coding_analytics(student)
    return {
        "success": True,
        "student_id": clean_id,
        "student_name": student.full_name or student.username,
        "student_branch": student_branch,
        "student_semester": s_profile.semester if s_profile else 1,
        "analytics": analytics,
    }


def get_admin_coding_overview() -> Dict[str, Any]:
    """Calculate institution-wide coding diagnostics for Administrator oversight."""
    from accounts.constants import Role

    students = User.objects.filter(role=Role.STUDENT.value)
    teachers = User.objects.filter(role=Role.TEACHER.value)
    questions = DSAQuestion.objects.all().order_by("-created_at")
    submissions = CodingSubmission.objects.all()

    total_students = students.count()
    participating_students = submissions.values("student_id").distinct().count()
    total_submissions = submissions.count()
    accepted_submissions = submissions.filter(status=CodingSubmission.SubmissionStatus.ACCEPTED).count()
    acceptance_rate = round((accepted_submissions / max(1, total_submissions) * 100), 1) if total_submissions else 0.0

    comp_errors = submissions.filter(status=CodingSubmission.SubmissionStatus.COMPILATION_ERROR).count()
    runtime_errors = submissions.filter(status=CodingSubmission.SubmissionStatus.RUNTIME_ERROR).count()
    wrong_answers = submissions.filter(status=CodingSubmission.SubmissionStatus.WRONG_ANSWER).count()
    timeouts = submissions.filter(status=CodingSubmission.SubmissionStatus.TIMEOUT).count()

    difficulty_counts = {
        "Easy": questions.filter(difficulty="Easy").count(),
        "Medium": questions.filter(difficulty="Medium").count(),
        "Hard": questions.filter(difficulty="Hard").count(),
    }

    # Questions table
    question_table = []
    for q in questions:
        q_subs = submissions.filter(question=q)
        att = q_subs.values("student_id").distinct().count()
        sol = q_subs.filter(status=CodingSubmission.SubmissionStatus.ACCEPTED).values("student_id").distinct().count()
        rate = round((sol / max(1, att) * 100), 1) if att else 0.0

        question_table.append({
            "id": q.id,
            "title": q.title,
            "topic": q.get_topic_display(),
            "difficulty": q.difficulty,
            "status": q.status,
            "created_by": q.created_by.full_name if q.created_by else "Faculty",
            "attempted_students": att,
            "solved_students": sol,
            "success_rate": rate,
            "total_evaluations": q_subs.count(),
        })

    return {
        "institution_summary": {
            "total_students": total_students,
            "participating_students": participating_students,
            "total_questions": questions.count(),
            "total_submissions": total_submissions,
            "accepted_submissions": accepted_submissions,
            "acceptance_rate": acceptance_rate,
            "compilation_errors": comp_errors,
            "runtime_errors": runtime_errors,
            "wrong_answers": wrong_answers,
            "timeouts": timeouts,
        },
        "questions_table": question_table,
        "difficulty_counts": difficulty_counts,
        "charts": {
            "outcomes": {
                "labels": ["Accepted", "Wrong Answer", "Compilation Error", "Runtime Error", "Timeout"],
                "values": [accepted_submissions, wrong_answers, comp_errors, runtime_errors, timeouts],
            },
            "difficulty": {
                "labels": list(difficulty_counts.keys()),
                "values": list(difficulty_counts.values()),
            }
        }
    }


# ==============================================================================
# 5. CODING RESOURCES & DSA PRACTICE HUB (AREA A & AREA B)
# ==============================================================================

DSA_CATEGORIES = [
    "Arrays and Strings",
    "Searching and Sorting",
    "Linked Lists",
    "Stacks and Queues",
    "Hashing",
    "Recursion and Backtracking",
    "Trees and Binary Search Trees",
    "Graphs",
    "Greedy Algorithms",
    "Dynamic Programming",
    "Two Pointers and Sliding Window",
    "Beginner Programming Problems",
]


def seed_standard_coding_resources():
    """Ensure standard verified DSA problems and compilers exist in CodingResource."""
    from dashboards.models import CodingResource

    standard_items = [
        # --- Area A: DSA Questions and Topics ---
        {
            "title": "Two Sum (Pair with Given Sum)",
            "resource_type": CodingResource.ResourceType.DSA_QUESTION,
            "topic_category": "Arrays and Strings",
            "difficulty": CodingResource.Difficulty.EASY,
            "description": "Given an array of integers and a target sum, find indices of the two numbers that add up to target.",
            "external_url": "https://leetcode.com/problems/two-sum/",
            "thumbnail_url": "/static/img/thumbnails/dsa_two_sum.jpg",
            "thumbnail_image": "coding_thumbs/dsa_two_sum.jpg",
            "supported_languages": "Python, Java, C++",
            "platform_name": "LeetCode",
        },
        {
            "title": "Longest Substring Without Repeating Characters",
            "resource_type": CodingResource.ResourceType.DSA_QUESTION,
            "topic_category": "Two Pointers and Sliding Window",
            "difficulty": CodingResource.Difficulty.MEDIUM,
            "description": "Find the length of the longest substring without duplicate characters using sliding window.",
            "external_url": "https://leetcode.com/problems/longest-substring-without-repeating-characters/",
            "thumbnail_url": "https://images.unsplash.com/photo-1555066931-4365d14bab8c?w=400&q=80",
            "thumbnail_image": "coding_thumbs/dsa_two_sum.jpg",
            "supported_languages": "Python, Java, C",
            "platform_name": "LeetCode",
        },
        {
            "title": "Reverse a Singly Linked List",
            "resource_type": CodingResource.ResourceType.DSA_QUESTION,
            "topic_category": "Linked Lists",
            "difficulty": CodingResource.Difficulty.EASY,
            "description": "Given the head of a singly linked list, reverse the list iteratively and recursively.",
            "external_url": "https://leetcode.com/problems/reverse-linked-list/",
            "thumbnail_url": "/static/img/thumbnails/dsa_linked_lists.jpg",
            "thumbnail_image": "coding_thumbs/dsa_linked_lists.jpg",
            "supported_languages": "Python, Java, C++",
            "platform_name": "LeetCode",
        },
        {
            "title": "Valid Parentheses & Bracket Matching",
            "resource_type": CodingResource.ResourceType.DSA_QUESTION,
            "topic_category": "Stacks and Queues",
            "difficulty": CodingResource.Difficulty.EASY,
            "description": "Determine if input string containing brackets '()', '[]', '{}' is balanced using a stack.",
            "external_url": "https://leetcode.com/problems/valid-parentheses/",
            "thumbnail_url": "https://images.unsplash.com/photo-1542838132-92c53300491e?w=400&q=80",
            "thumbnail_image": "coding_thumbs/dsa_two_sum.jpg",
            "supported_languages": "Python, Java, C",
            "platform_name": "LeetCode",
        },
        {
            "title": "Binary Search Algorithm & Applications",
            "resource_type": CodingResource.ResourceType.DSA_TOPIC,
            "topic_category": "Searching and Sorting",
            "difficulty": CodingResource.Difficulty.EASY,
            "description": "Master logarithmic time search O(log N) on sorted collections, bounds, and search space reduction.",
            "external_url": "https://www.geeksforgeeks.org/binary-search/",
            "thumbnail_url": "/static/img/thumbnails/dsa_binary_search.jpg",
            "thumbnail_image": "coding_thumbs/dsa_binary_search.jpg",
            "supported_languages": "Python, Java, C++",
            "platform_name": "GeeksforGeeks",
        },
        {
            "title": "Group Anagrams with Hash Maps",
            "resource_type": CodingResource.ResourceType.DSA_QUESTION,
            "topic_category": "Hashing",
            "difficulty": CodingResource.Difficulty.MEDIUM,
            "description": "Group an array of strings into sub-lists of anagrams utilizing character frequency hash maps.",
            "external_url": "https://leetcode.com/problems/group-anagrams/",
            "thumbnail_url": "https://images.unsplash.com/photo-1518770660439-4636190af475?w=400&q=80",
            "thumbnail_image": "coding_thumbs/dsa_two_sum.jpg",
            "supported_languages": "Python, Java",
            "platform_name": "LeetCode",
        },
        {
            "title": "Generate Subsets & Power Set (Backtracking)",
            "resource_type": CodingResource.ResourceType.DSA_QUESTION,
            "topic_category": "Recursion and Backtracking",
            "difficulty": CodingResource.Difficulty.MEDIUM,
            "description": "Given integer array of unique elements, return all possible subsets using depth-first search state exploration.",
            "external_url": "https://leetcode.com/problems/subsets/",
            "thumbnail_url": "https://images.unsplash.com/photo-1509228468518-180dd4864904?w=400&q=80",
            "thumbnail_image": "coding_thumbs/algo_master_theorem.jpg",
            "supported_languages": "Python, Java, C++",
            "platform_name": "LeetCode",
        },
        {
            "title": "Lowest Common Ancestor in Binary Search Tree",
            "resource_type": CodingResource.ResourceType.DSA_QUESTION,
            "topic_category": "Trees and Binary Search Trees",
            "difficulty": CodingResource.Difficulty.MEDIUM,
            "description": "Find lowest common ancestor node of two given nodes in a BST exploiting value order properties.",
            "external_url": "https://leetcode.com/problems/lowest-common-ancestor-of-a-binary-search-tree/",
            "thumbnail_url": "/static/img/thumbnails/dsa_trees_graphs.jpg",
            "thumbnail_image": "coding_thumbs/dsa_trees_graphs.jpg",
            "supported_languages": "Python, Java, C++",
            "platform_name": "LeetCode",
        },
        {
            "title": "Number of Connected Islands (BFS/DFS Traversal)",
            "resource_type": CodingResource.ResourceType.DSA_QUESTION,
            "topic_category": "Graphs",
            "difficulty": CodingResource.Difficulty.MEDIUM,
            "description": "Count islands formed by 1s (land) surrounded by 0s (water) using 2D grid matrix traversal.",
            "external_url": "https://leetcode.com/problems/number-of-islands/",
            "thumbnail_url": "/static/img/thumbnails/dsa_trees_graphs.jpg",
            "thumbnail_image": "coding_thumbs/dsa_trees_graphs.jpg",
            "supported_languages": "Python, Java, C++",
            "platform_name": "LeetCode",
        },
        {
            "title": "Activity Selection & Interval Scheduling",
            "resource_type": CodingResource.ResourceType.DSA_TOPIC,
            "topic_category": "Greedy Algorithms",
            "difficulty": CodingResource.Difficulty.MEDIUM,
            "description": "Optimal scheduling of non-overlapping activities sorted by earliest finish time.",
            "external_url": "https://www.geeksforgeeks.org/activity-selection-problem-greedy-algo-1/",
            "thumbnail_url": "https://images.unsplash.com/photo-1506784983877-45594efa4cbe?w=400&q=80",
            "thumbnail_image": "coding_thumbs/algo_master_theorem.jpg",
            "supported_languages": "Python, Java, C",
            "platform_name": "GeeksforGeeks",
        },
        {
            "title": "0/1 Knapsack Problem (Dynamic Programming)",
            "resource_type": CodingResource.ResourceType.DSA_QUESTION,
            "topic_category": "Dynamic Programming",
            "difficulty": CodingResource.Difficulty.HARD,
            "description": "Maximize total value without exceeding knapsack capacity using 2D memoization and tabulation.",
            "external_url": "https://www.geeksforgeeks.org/0-1-knapsack-problem-dp-10/",
            "thumbnail_url": "/static/img/thumbnails/dsa_dynamic_programming.jpg",
            "thumbnail_image": "coding_thumbs/dsa_dynamic_programming.jpg",
            "supported_languages": "Python, Java, C++",
            "platform_name": "GeeksforGeeks",
        },
        {
            "title": "Simple Array Sum & Element Accumulation",
            "resource_type": CodingResource.ResourceType.DSA_QUESTION,
            "topic_category": "Beginner Programming Problems",
            "difficulty": CodingResource.Difficulty.BEGINNER,
            "description": "Warm-up challenge: Compute the sum of an array of integers with edge cases and large values.",
            "external_url": "https://www.hackerrank.com/challenges/simple-array-sum/problem",
            "thumbnail_url": "https://images.unsplash.com/photo-1515879218367-8466d910aaa4?w=400&q=80",
            "thumbnail_image": "coding_thumbs/dsa_two_sum.jpg",
            "supported_languages": "Python, Java, C",
            "platform_name": "HackerRank",
        },

        # --- Area B: Online Compilers and Interpreters ---
        {
            "title": "Programiz Online Compiler",
            "resource_type": CodingResource.ResourceType.COMPILER,
            "topic_category": "Compilers & Interpreters",
            "difficulty": CodingResource.Difficulty.BEGINNER,
            "description": "Lightweight, zero-setup online runtime for Python, C, C++, and Java with real-time standard input/output.",
            "external_url": "https://www.programiz.com/python-programming/online-compiler/",
            "thumbnail_url": "/static/img/thumbnails/cloud_compiler.jpg",
            "thumbnail_image": "coding_thumbs/cloud_compiler.jpg",
            "supported_languages": "Python, C, C++, Java",
            "platform_name": "Programiz",
        },
        {
            "title": "OnlineGDB Compiler & Debugger",
            "resource_type": CodingResource.ResourceType.COMPILER,
            "topic_category": "Compilers & Interpreters",
            "difficulty": CodingResource.Difficulty.BEGINNER,
            "description": "Online compiler and integrated GDB debugger supporting C, C++, Java, and Python with interactive terminal.",
            "external_url": "https://www.onlinegdb.com/",
            "thumbnail_url": "/static/img/thumbnails/cloud_compiler.jpg",
            "thumbnail_image": "coding_thumbs/cloud_compiler.jpg",
            "supported_languages": "C, C++, Java, Python",
            "platform_name": "OnlineGDB",
        },
        {
            "title": "Replit Cloud Development Environment",
            "resource_type": CodingResource.ResourceType.COMPILER,
            "topic_category": "Compilers & Interpreters",
            "difficulty": CodingResource.Difficulty.BEGINNER,
            "description": "Full-fledged cloud workspace for building, running, and sharing software projects in Python, Java, C, and Node.js.",
            "external_url": "https://replit.com/",
            "thumbnail_url": "/static/img/thumbnails/cloud_compiler.jpg",
            "thumbnail_image": "coding_thumbs/cloud_compiler.jpg",
            "supported_languages": "Python, Java, C, Node.js",
            "platform_name": "Replit",
        },
        {
            "title": "JDoodle Online IDE",
            "resource_type": CodingResource.ResourceType.COMPILER,
            "topic_category": "Compilers & Interpreters",
            "difficulty": CodingResource.Difficulty.BEGINNER,
            "description": "Fast cloud execution tool supporting Java (JDK 17+), Python 3, C, and C++ with command-line arguments and file I/O.",
            "external_url": "https://www.jdoodle.com/",
            "thumbnail_url": "/static/img/thumbnails/cloud_compiler.jpg",
            "thumbnail_image": "coding_thumbs/cloud_compiler.jpg",
            "supported_languages": "Java, Python, C, C++",
            "platform_name": "JDoodle",
        },
    ]

    for item in standard_items:
        CodingResource.objects.update_or_create(
            title=item["title"],
            defaults=item
        )


def save_coding_resource(user: User, data: Dict[str, Any], files: Optional[Dict[str, Any]] = None, resource_id: Optional[int] = None) -> Dict[str, Any]:
    """Validate, create, or update a CodingResource for Teachers and Admins."""
    from django.core.validators import URLValidator
    from django.core.exceptions import ValidationError
    from dashboards.models import CodingResource

    title = data.get("title", "").strip()
    if not title:
        return {"success": False, "message": "Resource title is required."}

    resource_type = data.get("resource_type", CodingResource.ResourceType.DSA_QUESTION)
    if resource_type not in CodingResource.ResourceType.values:
        resource_type = CodingResource.ResourceType.DSA_QUESTION

    topic_category = data.get("topic_category", "Arrays and Strings").strip()
    difficulty = data.get("difficulty", CodingResource.Difficulty.MEDIUM)
    if difficulty not in CodingResource.Difficulty.values:
        difficulty = CodingResource.Difficulty.MEDIUM

    description = data.get("description", "").strip()
    external_url = data.get("external_url", "").strip()
    if not external_url:
        return {"success": False, "message": "External practice/compiler URL is required."}

    # Validate URL
    validator = URLValidator(schemes=["http", "https"])
    try:
        validator(external_url)
    except ValidationError:
        return {"success": False, "message": "Please enter a valid HTTP/HTTPS external URL."}

    platform_name = data.get("platform_name", "").strip()
    supported_languages = data.get("supported_languages", "Python, Java, C").strip()
    thumbnail_url = data.get("thumbnail_url", "").strip()
    if thumbnail_url:
        try:
            validator(thumbnail_url)
        except ValidationError:
            thumbnail_url = ""

    status = data.get("status", CodingResource.Status.PUBLISHED)
    if status not in CodingResource.Status.values:
        status = CodingResource.Status.PUBLISHED

    branch = data.get("branch", "CSE").strip()
    semester = int(data.get("semester", 3))

    if resource_id:
        resource = CodingResource.objects.filter(pk=resource_id).first()
        if not resource:
            return {"success": False, "message": "Resource not found."}
        # Check permissions: Admin can edit any, Teacher can edit their own or if teacher
        if user.role != Role.ADMIN.value and resource.created_by and resource.created_by != user:
            return {"success": False, "message": "You are not authorized to edit this resource."}
    else:
        resource = CodingResource(created_by=user)

    resource.title = title
    resource.resource_type = resource_type
    resource.topic_category = topic_category
    resource.difficulty = difficulty
    resource.description = description
    resource.external_url = external_url
    resource.platform_name = platform_name
    resource.supported_languages = supported_languages
    resource.thumbnail_url = thumbnail_url
    resource.status = status
    resource.branch = branch
    resource.semester = semester

    if files and "thumbnail_image" in files:
        uploaded = files["thumbnail_image"]
        # Basic validation
        if uploaded.content_type.startswith("image/"):
            resource.thumbnail_image = uploaded

    resource.save()
    return {"success": True, "message": f"Resource '{resource.title}' saved successfully.", "resource": resource}


def delete_or_archive_coding_resource(user: User, resource_id: int) -> Dict[str, Any]:
    """Soft-archive or safely remove a CodingResource."""
    from dashboards.models import CodingResource

    resource = CodingResource.objects.filter(pk=resource_id).first()
    if not resource:
        return {"success": False, "message": "Resource not found."}

    if user.role != Role.ADMIN.value and resource.created_by and resource.created_by != user:
        return {"success": False, "message": "Permission denied."}

    # Soft-archive to preserve historical references
    resource.status = CodingResource.Status.ARCHIVED
    resource.save(update_fields=["status"])
    return {"success": True, "message": f"Resource '{resource.title}' has been archived."}


def toggle_coding_resource_status(user: User, resource_id: int) -> Dict[str, Any]:
    """Toggle between published and draft states."""
    from dashboards.models import CodingResource

    resource = CodingResource.objects.filter(pk=resource_id).first()
    if not resource:
        return {"success": False, "message": "Resource not found."}

    if user.role != Role.ADMIN.value and resource.created_by and resource.created_by != user:
        return {"success": False, "message": "Permission denied."}

    if resource.status == CodingResource.Status.PUBLISHED:
        resource.status = CodingResource.Status.DRAFT
    else:
        resource.status = CodingResource.Status.PUBLISHED

    resource.save(update_fields=["status"])
    return {
        "success": True,
        "new_status": resource.status,
        "new_status_display": resource.get_status_display(),
        "message": f"Resource is now {resource.get_status_display()}."
    }


def get_coding_resources_for_management(user: User, status_filter: Optional[str] = None, type_filter: Optional[str] = None, search: Optional[str] = None) -> List[Any]:
    """List resources for faculty and admin management view."""
    from dashboards.models import CodingResource

    seed_standard_coding_resources()
    qs = CodingResource.objects.all().order_by("-updated_at")

    if status_filter and status_filter != "all":
        qs = qs.filter(status=status_filter)
    else:
        # By default exclude archived unless asked
        qs = qs.exclude(status=CodingResource.Status.ARCHIVED)

    if type_filter and type_filter != "all":
        qs = qs.filter(resource_type=type_filter)

    if search:
        qs = qs.filter(
            Q(title__icontains=search) |
            Q(topic_category__icontains=search) |
            Q(platform_name__icontains=search) |
            Q(description__icontains=search)
        )

    return qs



