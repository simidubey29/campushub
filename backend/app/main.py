# ============================================================
# CAMPUSHUB - STUDENT ACADEMIC PORTAL
# FastAPI Backend
# ============================================================

import os
from datetime import datetime, timedelta, date
from typing import Optional

from dotenv import load_dotenv

from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    status,
    Query,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from jose import jwt, JWTError
from passlib.context import CryptContext

from sqlalchemy.orm import Session
from sqlalchemy import or_

from .database import get_db
from .models import (
    User,
    Assignment,
    AssignmentStudent,
    Submission,
    Mark,
    Attendance,
    Notice,
    Timetable,
    Project,
    ProjectMember,
    Task,
)

from .schemas import (
    Login,
    StudentRegister,
    AdminUserCreate,
    AssignmentCreate,
    AssignmentSubmit,
    GradeSubmission,
    MarkCreate,
    AttendanceCreate,
    NoticeCreate,
    ProjectCreate,
    TaskCreate,
    TaskStatus,
)


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()

SECRET = os.getenv("JWT_SECRET")

if not SECRET:
    raise RuntimeError(
        "JWT_SECRET is missing. "
        "Please add JWT_SECRET to backend/.env"
    )

ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 8


# ============================================================
# PASSWORD / AUTH
# ============================================================

pwd = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)

security = HTTPBearer()


# ============================================================
# FASTAPI APP
# ============================================================

app = FastAPI(
    title="CampusHUB Academic Portal API",
    description="Role-based Student Academic Portal",
    version="2.0.0",
)


# ============================================================
# CORS
# IMPORTANT FIX FOR:
# OPTIONS /api/auth/login 400 Bad Request
# NetworkError when attempting to fetch resource
# ============================================================

FRONTEND_URL = os.getenv(
    "FRONTEND_URL",
    "http://localhost:5173"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        FRONTEND_URL,
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# GENERAL HELPERS
# ============================================================


def user_dict(user: User):
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "student_id": user.student_id,
        "department": user.department,
        "semester": user.semester,
    }


def create_token(user: User):
    expire = datetime.utcnow() + timedelta(
        hours=TOKEN_EXPIRE_HOURS
    )

    payload = {
        "sub": str(user.id),
        "role": user.role,
        "exp": expire,
    }

    return jwt.encode(
        payload,
        SECRET,
        algorithm=ALGORITHM,
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            SECRET,
            algorithms=[ALGORITHM],
        )

        user_id = payload.get("sub")

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )

        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )

        user = (
            db.query(User)
            .filter(User.id == user_id)
            .first()
        )

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )

        return user

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


def require_roles(*roles):
    def checker(
        user: User = Depends(get_current_user),
    ):
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Access denied. Required role: "
                    + ", ".join(roles)
                ),
            )

        return user

    return checker


def assignment_to_dict(
    assignment: Assignment,
    db: Session,
    current_user: Optional[User] = None,
):
    student_links = (
        db.query(AssignmentStudent)
        .filter(
            AssignmentStudent.assignment_id
            == assignment.id
        )
        .all()
    )

    student_ids = [
        link.student_id
        for link in student_links
    ]

    submission = None

    if current_user:
        submission = (
            db.query(Submission)
            .filter(
                Submission.assignment_id
                == assignment.id,
                Submission.student_id
                == current_user.id,
            )
            .first()
        )

    return {
        "id": assignment.id,
        "title": assignment.title,
        "description": assignment.description,
        "subject": assignment.subject,
        "deadline": assignment.deadline,
        "faculty_id": assignment.faculty_id,
        "max_marks": assignment.max_marks,
        "created_at": assignment.created_at,
        "student_ids": student_ids,
        "submission": (
            {
                "id": submission.id,
                "submission_text": submission.submission_text,
                "submitted_at": submission.submitted_at,
                "status": submission.status,
                "marks": submission.marks,
                "feedback": submission.feedback,
            }
            if submission
            else None
        ),
    }


# ============================================================
# HEALTH
# ============================================================


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "message": "CampusHUB backend is running",
        "database": "MySQL",
    }


# ============================================================
# AUTHENTICATION
# ============================================================


@app.post("/api/auth/login")
def login(
    data: Login,
    db: Session = Depends(get_db),
):
    user = (
        db.query(User)
        .filter(User.email == data.email)
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account password is not configured",
        )

    try:
        password_valid = pwd.verify(
            data.password,
            user.password_hash,
        )
    except Exception:
        password_valid = False

    if not password_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_token(user)

    return {
        "token": token,
        "user": user_dict(user),
    }


# ============================================================
# STUDENT REGISTRATION
# Public registration can ONLY create students.
# Admin/Faculty cannot be created through this endpoint.
# ============================================================


@app.post("/api/auth/register")
def register_student(
    data: StudentRegister,
    db: Session = Depends(get_db),
):
    existing_email = (
        db.query(User)
        .filter(User.email == data.email)
        .first()
    )

    if existing_email:
        raise HTTPException(
            status_code=400,
            detail="Email already registered",
        )

    existing_student_id = (
        db.query(User)
        .filter(User.student_id == data.student_id)
        .first()
    )

    if existing_student_id:
        raise HTTPException(
            status_code=400,
            detail="Student ID already exists",
        )

    user = User(
        name=data.name,
        email=data.email,
        password_hash=pwd.hash(data.password),
        role="student",
        student_id=data.student_id,
        department=data.department,
        semester=data.semester,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "message": "Student registration successful",
        "user": user_dict(user),
    }


# ============================================================
# ADMIN - USER MANAGEMENT
# ============================================================


@app.get("/api/admin/users")
def get_users(
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles("admin")),
):
    users = (
        db.query(User)
        .order_by(User.id.desc())
        .all()
    )

    return [
        user_dict(user)
        for user in users
    ]


@app.post("/api/admin/users")
def create_user(
    data: AdminUserCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles("admin")),
):
    allowed_roles = {
        "student",
        "faculty",
        "admin",
    }

    if data.role not in allowed_roles:
        raise HTTPException(
            status_code=400,
            detail="Invalid role",
        )

    existing = (
        db.query(User)
        .filter(User.email == data.email)
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Email already exists",
        )

    if data.student_id:
        student_exists = (
            db.query(User)
            .filter(
                User.student_id
                == data.student_id
            )
            .first()
        )

        if student_exists:
            raise HTTPException(
                status_code=400,
                detail="Student ID already exists",
            )

    user = User(
        name=data.name,
        email=data.email,
        password_hash=pwd.hash(data.password),
        role=data.role,
        student_id=data.student_id,
        department=data.department,
        semester=data.semester,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "message": "User created successfully",
        "user": user_dict(user),
    }


@app.delete("/api/admin/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles("admin")),
):
    if user_id == admin.id:
        raise HTTPException(
            status_code=400,
            detail="You cannot delete your own admin account",
        )

    user = (
        db.query(User)
        .filter(User.id == user_id)
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    db.delete(user)
    db.commit()

    return {
        "message": "User deleted successfully"
    }


# ============================================================
# DASHBOARD
# ============================================================


@app.get("/api/dashboard")
def dashboard(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # --------------------------------------------------------
    # STUDENT DASHBOARD
    # --------------------------------------------------------

    if user.role == "student":

        assignment_links = (
            db.query(AssignmentStudent)
            .filter(
                AssignmentStudent.student_id
                == user.id
            )
            .all()
        )

        assignment_ids = [
            x.assignment_id
            for x in assignment_links
        ]

        assignments = []

        if assignment_ids:
            assignments = (
                db.query(Assignment)
                .filter(
                    Assignment.id.in_(
                        assignment_ids
                    )
                )
                .all()
            )

        submissions = (
            db.query(Submission)
            .filter(
                Submission.student_id
                == user.id
            )
            .all()
        )

        marks = (
            db.query(Mark)
            .filter(
                Mark.student_id == user.id
            )
            .all()
        )

        attendance_records = (
            db.query(Attendance)
            .filter(
                Attendance.student_id
                == user.id
            )
            .all()
        )

        notices = (
            db.query(Notice)
            .order_by(
                Notice.created_at.desc()
            )
            .limit(5)
            .all()
        )

        submitted_count = len(
            [
                s for s in submissions
                if s.status in (
                    "Submitted",
                    "Late",
                )
            ]
        )

        pending_count = max(
            len(assignments)
            - submitted_count,
            0,
        )

        present_count = len(
            [
                a for a in attendance_records
                if str(a.status).lower()
                == "present"
            ]
        )

        attendance_percentage = (
            round(
                present_count
                / len(attendance_records)
                * 100,
                1,
            )
            if attendance_records
            else 0
        )

        marks_percentage = (
            round(
                sum(
                    m.marks
                    for m in marks
                )
                / sum(
                    m.max_marks
                    for m in marks
                )
                * 100,
                1,
            )
            if marks and sum(
                m.max_marks
                for m in marks
            ) > 0
            else 0
        )

        return {
            "role": "student",
            "user": user_dict(user),
            "stats": {
                "assignments": len(assignments),
                "submitted": submitted_count,
                "pending": pending_count,
                "attendance": attendance_percentage,
                "average_marks": marks_percentage,
            },
            "recent_notices": [
                {
                    "id": n.id,
                    "title": n.title,
                    "message": n.message,
                    "created_at": n.created_at,
                }
                for n in notices
            ],
        }

    # --------------------------------------------------------
    # FACULTY DASHBOARD
    # --------------------------------------------------------

    if user.role == "faculty":

        assignments_count = (
            db.query(Assignment)
            .filter(
                Assignment.faculty_id
                == user.id
            )
            .count()
        )

        student_count = (
            db.query(User)
            .filter(User.role == "student")
            .count()
        )

        submission_count = (
            db.query(Submission)
            .join(
                Assignment,
                Submission.assignment_id
                == Assignment.id,
            )
            .filter(
                Assignment.faculty_id
                == user.id
            )
            .count()
        )

        notices_count = (
            db.query(Notice)
            .count()
        )

        return {
            "role": "faculty",
            "user": user_dict(user),
            "stats": {
                "assignments": assignments_count,
                "students": student_count,
                "submissions": submission_count,
                "notices": notices_count,
            },
        }

    # --------------------------------------------------------
    # ADMIN DASHBOARD
    # --------------------------------------------------------

    if user.role == "admin":

        students = (
            db.query(User)
            .filter(User.role == "student")
            .count()
        )

        faculty = (
            db.query(User)
            .filter(User.role == "faculty")
            .count()
        )

        admins = (
            db.query(User)
            .filter(User.role == "admin")
            .count()
        )

        assignments = (
            db.query(Assignment)
            .count()
        )

        submissions = (
            db.query(Submission)
            .count()
        )

        projects = (
            db.query(Project)
            .count()
        )

        notices = (
            db.query(Notice)
            .count()
        )

        return {
            "role": "admin",
            "user": user_dict(user),
            "stats": {
                "students": students,
                "faculty": faculty,
                "admins": admins,
                "assignments": assignments,
                "submissions": submissions,
                "projects": projects,
                "notices": notices,
            },
        }

    raise HTTPException(
        status_code=403,
        detail="Invalid user role",
    )


# ============================================================
# ASSIGNMENTS - GET
# ============================================================


@app.get("/api/assignments")
def get_assignments(
    search: Optional[str] = Query(
        default=None
    ),
    subject: Optional[str] = Query(
        default=None
    ),
    status_filter: Optional[str] = Query(
        default=None
    ),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # --------------------------------------------------------
    # STUDENT
    # --------------------------------------------------------

    if user.role == "student":

        links = (
            db.query(AssignmentStudent)
            .filter(
                AssignmentStudent.student_id
                == user.id
            )
            .all()
        )

        ids = [
            x.assignment_id
            for x in links
        ]

        if not ids:
            return []

        query = (
            db.query(Assignment)
            .filter(
                Assignment.id.in_(ids)
            )
        )

    # --------------------------------------------------------
    # FACULTY
    # --------------------------------------------------------

    elif user.role == "faculty":

        query = (
            db.query(Assignment)
            .filter(
                Assignment.faculty_id
                == user.id
            )
        )

    # --------------------------------------------------------
    # ADMIN
    # --------------------------------------------------------

    else:
        query = db.query(Assignment)

    if search:
        pattern = f"%{search}%"

        query = query.filter(
            or_(
                Assignment.title.ilike(pattern),
                Assignment.subject.ilike(pattern),
                Assignment.description.ilike(pattern),
            )
        )

    if subject:
        query = query.filter(
            Assignment.subject.ilike(
                f"%{subject}%"
            )
        )

    assignments = (
        query
        .order_by(Assignment.deadline.asc())
        .all()
    )

    result = []

    for assignment in assignments:

        data = assignment_to_dict(
            assignment,
            db,
            user,
        )

        if status_filter:

            current_status = (
                data["submission"]["status"]
                if data["submission"]
                else "Not Submitted"
            )

            if (
                current_status.lower()
                != status_filter.lower()
            ):
                continue

        result.append(data)

    return result


# ============================================================
# ASSIGNMENT - CREATE
# ============================================================


@app.post("/api/assignments")
def create_assignment(
    data: AssignmentCreate,
    user: User = Depends(
        require_roles("faculty", "admin")
    ),
    db: Session = Depends(get_db),
):
    if not data.student_ids:
        raise HTTPException(
            status_code=400,
            detail="Select at least one student",
        )

    assignment = Assignment(
        title=data.title,
        description=data.description,
        subject=data.subject,
        deadline=data.deadline,
        faculty_id=user.id,
        max_marks=data.max_marks,
    )

    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    for student_id in data.student_ids:

        student = (
            db.query(User)
            .filter(
                User.id == student_id,
                User.role == "student",
            )
            .first()
        )

        if not student:
            continue

        link = AssignmentStudent(
            assignment_id=assignment.id,
            student_id=student.id,
        )

        db.add(link)

        submission = Submission(
            assignment_id=assignment.id,
            student_id=student.id,
            submission_text=None,
            submitted_at=None,
            status="Not Submitted",
        )

        db.add(submission)

    db.commit()

    return {
        "message": "Assignment created successfully",
        "id": assignment.id,
    }


# ============================================================
# ASSIGNMENT - SINGLE
# ============================================================


@app.get("/api/assignments/{assignment_id}")
def get_assignment(
    assignment_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assignment = (
        db.query(Assignment)
        .filter(
            Assignment.id == assignment_id
        )
        .first()
    )

    if not assignment:
        raise HTTPException(
            status_code=404,
            detail="Assignment not found",
        )

    if user.role == "student":

        assigned = (
            db.query(AssignmentStudent)
            .filter(
                AssignmentStudent.assignment_id
                == assignment_id,
                AssignmentStudent.student_id
                == user.id,
            )
            .first()
        )

        if not assigned:
            raise HTTPException(
                status_code=403,
                detail="Assignment not assigned to you",
            )

    elif (
        user.role == "faculty"
        and assignment.faculty_id != user.id
    ):
        raise HTTPException(
            status_code=403,
            detail="You do not own this assignment",
        )

    return assignment_to_dict(
        assignment,
        db,
        user,
    )


# ============================================================
# ASSIGNMENT - SUBMIT
# ============================================================


@app.post(
    "/api/assignments/{assignment_id}/submit"
)
def submit_assignment(
    assignment_id: int,
    data: AssignmentSubmit,
    user: User = Depends(
        require_roles("student")
    ),
    db: Session = Depends(get_db),
):
    assignment = (
        db.query(Assignment)
        .filter(
            Assignment.id == assignment_id
        )
        .first()
    )

    if not assignment:
        raise HTTPException(
            status_code=404,
            detail="Assignment not found",
        )

    assigned = (
        db.query(AssignmentStudent)
        .filter(
            AssignmentStudent.assignment_id
            == assignment_id,
            AssignmentStudent.student_id
            == user.id,
        )
        .first()
    )

    if not assigned:
        raise HTTPException(
            status_code=403,
            detail="This assignment is not assigned to you",
        )

    submission = (
        db.query(Submission)
        .filter(
            Submission.assignment_id
            == assignment_id,
            Submission.student_id
            == user.id,
        )
        .first()
    )

    if not submission:

        submission = Submission(
            assignment_id=assignment_id,
            student_id=user.id,
        )

        db.add(submission)

    # --------------------------------------------------------
    # SUBMISSION TIME
    # --------------------------------------------------------

    now = datetime.utcnow()

    submission.submission_text = (
        data.submission_text
    )

    submission.submitted_at = now

    # Automatic late detection
    if now > assignment.deadline:
        submission.status = "Late"
    else:
        submission.status = "Submitted"

    db.commit()
    db.refresh(submission)

    return {
        "message": "Assignment submitted successfully",
        "submission_id": submission.id,
        "submitted_at": submission.submitted_at,
        "status": submission.status,
    }


# ============================================================
# ASSIGNMENT SUBMISSIONS - FACULTY
# ============================================================


@app.get(
    "/api/assignments/{assignment_id}/submissions"
)
def get_submissions(
    assignment_id: int,
    user: User = Depends(
        require_roles("faculty", "admin")
    ),
    db: Session = Depends(get_db),
):
    assignment = (
        db.query(Assignment)
        .filter(
            Assignment.id == assignment_id
        )
        .first()
    )

    if not assignment:
        raise HTTPException(
            status_code=404,
            detail="Assignment not found",
        )

    if (
        user.role == "faculty"
        and assignment.faculty_id != user.id
    ):
        raise HTTPException(
            status_code=403,
            detail="You do not own this assignment",
        )

    submissions = (
        db.query(Submission)
        .filter(
            Submission.assignment_id
            == assignment_id
        )
        .all()
    )

    result = []

    for submission in submissions:

        student = (
            db.query(User)
            .filter(
                User.id
                == submission.student_id
            )
            .first()
        )

        result.append(
            {
                "id": submission.id,
                "assignment_id": submission.assignment_id,
                "student": (
                    user_dict(student)
                    if student
                    else None
                ),
                "submission_text": (
                    submission.submission_text
                ),
                "submitted_at": (
                    submission.submitted_at
                ),
                "status": submission.status,
                "marks": submission.marks,
                "feedback": submission.feedback,
            }
        )

    return result


# ============================================================
# GRADE SUBMISSION
# ============================================================


@app.put(
    "/api/submissions/{submission_id}/grade"
)
def grade_submission(
    submission_id: int,
    data: GradeSubmission,
    user: User = Depends(
        require_roles("faculty", "admin")
    ),
    db: Session = Depends(get_db),
):
    submission = (
        db.query(Submission)
        .filter(
            Submission.id == submission_id
        )
        .first()
    )

    if not submission:
        raise HTTPException(
            status_code=404,
            detail="Submission not found",
        )

    assignment = (
        db.query(Assignment)
        .filter(
            Assignment.id
            == submission.assignment_id
        )
        .first()
    )

    if (
        user.role == "faculty"
        and assignment.faculty_id != user.id
    ):
        raise HTTPException(
            status_code=403,
            detail="You cannot grade this submission",
        )

    if data.marks < 0:
        raise HTTPException(
            status_code=400,
            detail="Marks cannot be negative",
        )

    if data.marks > assignment.max_marks:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Marks cannot exceed "
                f"{assignment.max_marks}"
            ),
        )

    submission.marks = data.marks
    submission.feedback = data.feedback

    db.commit()
    db.refresh(submission)

    return {
        "message": "Submission graded successfully",
        "marks": submission.marks,
        "feedback": submission.feedback,
    }


# ============================================================
# MARKS - GET
# ============================================================


@app.get("/api/marks")
def get_marks(
    student_id: Optional[int] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role == "student":

        target_student_id = user.id

    else:

        if student_id is None:
            raise HTTPException(
                status_code=400,
                detail="student_id is required",
            )

        target_student_id = student_id

    marks = (
        db.query(Mark)
        .filter(
            Mark.student_id
            == target_student_id
        )
        .order_by(Mark.created_at.desc())
        .all()
    )

    return [
        {
            "id": mark.id,
            "student_id": mark.student_id,
            "subject": mark.subject,
            "exam": mark.exam,
            "marks": mark.marks,
            "max_marks": mark.max_marks,
            "percentage": (
                round(
                    mark.marks
                    / mark.max_marks
                    * 100,
                    2,
                )
                if mark.max_marks
                else 0
            ),
            "created_at": mark.created_at,
        }
        for mark in marks
    ]


# ============================================================
# MARKS - CREATE
# ============================================================


@app.post("/api/marks")
def create_mark(
    data: MarkCreate,
    user: User = Depends(
        require_roles("faculty", "admin")
    ),
    db: Session = Depends(get_db),
):
    student = (
        db.query(User)
        .filter(
            User.id == data.student_id,
            User.role == "student",
        )
        .first()
    )

    if not student:
        raise HTTPException(
            status_code=404,
            detail="Student not found",
        )

    if data.marks < 0:
        raise HTTPException(
            status_code=400,
            detail="Marks cannot be negative",
        )

    if data.marks > data.max_marks:
        raise HTTPException(
            status_code=400,
            detail="Marks cannot exceed max marks",
        )

    mark = Mark(
        student_id=data.student_id,
        subject=data.subject,
        exam=data.exam,
        marks=data.marks,
        max_marks=data.max_marks,
    )

    db.add(mark)
    db.commit()
    db.refresh(mark)

    return {
        "message": "Marks added successfully",
        "id": mark.id,
    }


# ============================================================
# MARKS ANALYTICS
# ============================================================


@app.get("/api/marks/analytics")
def marks_analytics(
    student_id: Optional[int] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role == "student":
        target_id = user.id
    else:
        if student_id is None:
            raise HTTPException(
                status_code=400,
                detail="student_id is required",
            )

        target_id = student_id

    marks = (
        db.query(Mark)
        .filter(
            Mark.student_id == target_id
        )
        .all()
    )

    if not marks:
        return {
            "total_exams": 0,
            "average_percentage": 0,
            "subject_wise": [],
        }

    total_marks = sum(
        x.marks for x in marks
    )

    total_max = sum(
        x.max_marks for x in marks
    )

    average = (
        round(
            total_marks
            / total_max
            * 100,
            2,
        )
        if total_max
        else 0
    )

    subject_data = {}

    for mark in marks:

        if mark.subject not in subject_data:
            subject_data[mark.subject] = {
                "subject": mark.subject,
                "marks": 0,
                "max_marks": 0,
            }

        subject_data[
            mark.subject
        ]["marks"] += mark.marks

        subject_data[
            mark.subject
        ]["max_marks"] += mark.max_marks

    subject_wise = []

    for item in subject_data.values():

        percentage = (
            round(
                item["marks"]
                / item["max_marks"]
                * 100,
                2,
            )
            if item["max_marks"]
            else 0
        )

        subject_wise.append(
            {
                "subject": item["subject"],
                "marks": item["marks"],
                "max_marks": item["max_marks"],
                "percentage": percentage,
            }
        )

    return {
        "total_exams": len(marks),
        "average_percentage": average,
        "subject_wise": subject_wise,
    }


# ============================================================
# ATTENDANCE - GET
# ============================================================


@app.get("/api/attendance")
def get_attendance(
    student_id: Optional[int] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role == "student":
        target_id = user.id
    else:
        if student_id is None:
            raise HTTPException(
                status_code=400,
                detail="student_id is required",
            )

        target_id = student_id

    records = (
        db.query(Attendance)
        .filter(
            Attendance.student_id
            == target_id
        )
        .order_by(
            Attendance.attendance_date.desc()
        )
        .all()
    )

    result = []

    for record in records:
        result.append(
            {
                "id": record.id,
                "student_id": record.student_id,
                "subject": record.subject,
                "attendance_date": record.attendance_date,
                "status": record.status,
            }
        )

    return result


# ============================================================
# ATTENDANCE ANALYTICS
# ============================================================


@app.get("/api/attendance/analytics")
def attendance_analytics(
    student_id: Optional[int] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role == "student":
        target_id = user.id
    else:
        if student_id is None:
            raise HTTPException(
                status_code=400,
                detail="student_id is required",
            )

        target_id = student_id

    records = (
        db.query(Attendance)
        .filter(
            Attendance.student_id
            == target_id
        )
        .all()
    )

    total = len(records)

    present = len(
        [
            x for x in records
            if str(x.status).lower()
            == "present"
        ]
    )

    absent = total - present

    percentage = (
        round(
            present / total * 100,
            2,
        )
        if total
        else 0
    )

    subject_data = {}

    for record in records:

        subject = record.subject

        if subject not in subject_data:
            subject_data[subject] = {
                "subject": subject,
                "total": 0,
                "present": 0,
            }

        subject_data[subject]["total"] += 1

        if (
            str(record.status).lower()
            == "present"
        ):
            subject_data[
                subject
            ]["present"] += 1

    subject_wise = []

    for item in subject_data.values():

        subject_percentage = (
            round(
                item["present"]
                / item["total"]
                * 100,
                2,
            )
            if item["total"]
            else 0
        )

        subject_wise.append(
            {
                **item,
                "percentage": subject_percentage,
            }
        )

    return {
        "total_classes": total,
        "present": present,
        "absent": absent,
        "percentage": percentage,
        "subject_wise": subject_wise,
    }


# ============================================================
# ATTENDANCE - CREATE
# ============================================================


@app.post("/api/attendance")
def create_attendance(
    data: AttendanceCreate,
    user: User = Depends(
        require_roles("faculty", "admin")
    ),
    db: Session = Depends(get_db),
):
    student = (
        db.query(User)
        .filter(
            User.id == data.student_id,
            User.role == "student",
        )
        .first()
    )

    if not student:
        raise HTTPException(
            status_code=404,
            detail="Student not found",
        )

    if data.status not in (
        "Present",
        "Absent",
    ):
        raise HTTPException(
            status_code=400,
            detail="Status must be Present or Absent",
        )

    try:
        attendance_date = date.fromisoformat(
            data.attendance_date
        )
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date. Use YYYY-MM-DD",
        )

    record = Attendance(
        student_id=data.student_id,
        subject=data.subject,
        attendance_date=attendance_date,
        status=data.status,
    )

    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "message": "Attendance recorded successfully",
        "id": record.id,
    }


# ============================================================
# NOTICES - GET
# ============================================================


@app.get("/api/notices")
def get_notices(
    search: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Notice)

    if search:
        pattern = f"%{search}%"

        query = query.filter(
            or_(
                Notice.title.ilike(pattern),
                Notice.message.ilike(pattern),
            )
        )

    notices = (
        query
        .order_by(
            Notice.created_at.desc()
        )
        .all()
    )

    return [
        {
            "id": n.id,
            "title": n.title,
            "message": n.message,
            "created_by": n.created_by,
            "created_at": n.created_at,
        }
        for n in notices
    ]


# ============================================================
# NOTICES - CREATE
# ============================================================


@app.post("/api/notices")
def create_notice(
    data: NoticeCreate,
    user: User = Depends(
        require_roles("faculty", "admin")
    ),
    db: Session = Depends(get_db),
):
    notice = Notice(
        title=data.title,
        message=data.message,
        created_by=user.id,
    )

    db.add(notice)
    db.commit()
    db.refresh(notice)

    return {
        "message": "Notice published successfully",
        "id": notice.id,
    }


# ============================================================
# TIMETABLE
# ============================================================


@app.get("/api/timetable")
def get_timetable(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Timetable)
        .order_by(Timetable.id.asc())
        .all()
    )

    return [
        {
            "id": row.id,
            "day": row.day,
            "time": row.time,
            "subject": row.subject,
            "faculty": row.faculty,
            "room": row.room,
        }
        for row in rows
    ]


# ============================================================
# PROJECTS - GET
# ============================================================


@app.get("/api/projects")
def get_projects(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role == "admin":

        projects = (
            db.query(Project)
            .order_by(Project.id.desc())
            .all()
        )

    else:

        projects = (
            db.query(Project)
            .filter(
                Project.owner_id == user.id
            )
            .order_by(Project.id.desc())
            .all()
        )

    result = []

    for project in projects:

        members = (
            db.query(ProjectMember)
            .filter(
                ProjectMember.project_id
                == project.id
            )
            .all()
        )

        tasks = (
            db.query(Task)
            .filter(
                Task.project_id
                == project.id
            )
            .all()
        )

        result.append(
            {
                "id": project.id,
                "name": project.name,
                "description": project.description,
                "deadline": project.deadline,
                "status": project.status,
                "owner_id": project.owner_id,
                "members": [
                    member.user_id
                    for member in members
                ],
                "tasks": [
                    {
                        "id": task.id,
                        "title": task.title,
                        "assigned_to": task.assigned_to,
                        "deadline": task.deadline,
                        "status": task.status,
                    }
                    for task in tasks
                ],
            }
        )

    return result


# ============================================================
# PROJECT - CREATE
# ============================================================


@app.post("/api/projects")
def create_project(
    data: ProjectCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = Project(
        name=data.name,
        description=data.description,
        deadline=data.deadline,
        status="Planning",
        owner_id=user.id,
    )

    db.add(project)
    db.commit()
    db.refresh(project)

    # Owner automatically becomes member
    member = ProjectMember(
        project_id=project.id,
        user_id=user.id,
    )

    db.add(member)
    db.commit()

    return {
        "message": "Project created successfully",
        "id": project.id,
    }


# ============================================================
# PROJECT MEMBERS
# ============================================================


@app.post("/api/projects/{project_id}/members/{user_id}")
def add_project_member(
    project_id: int,
    user_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = (
        db.query(Project)
        .filter(Project.id == project_id)
        .first()
    )

    if not project:
        raise HTTPException(
            status_code=404,
            detail="Project not found",
        )

    if (
        user.role != "admin"
        and project.owner_id != user.id
    ):
        raise HTTPException(
            status_code=403,
            detail="Only project owner or admin can add members",
        )

    target = (
        db.query(User)
        .filter(User.id == user_id)
        .first()
    )

    if not target:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    existing = (
        db.query(ProjectMember)
        .filter(
            ProjectMember.project_id
            == project_id,
            ProjectMember.user_id
            == user_id,
        )
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=400,
            detail="User is already a project member",
        )

    member = ProjectMember(
        project_id=project_id,
        user_id=user_id,
    )

    db.add(member)
    db.commit()

    return {
        "message": "Project member added successfully"
    }


# ============================================================
# TASK - CREATE
# ============================================================


@app.post("/api/tasks")
def create_task(
    data: TaskCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = (
        db.query(Project)
        .filter(
            Project.id == data.project_id
        )
        .first()
    )

    if not project:
        raise HTTPException(
            status_code=404,
            detail="Project not found",
        )

    if (
        user.role != "admin"
        and project.owner_id != user.id
    ):
        raise HTTPException(
            status_code=403,
            detail="Only project owner or admin can create tasks",
        )

    if data.assigned_to:

        assigned_user = (
            db.query(User)
            .filter(
                User.id
                == data.assigned_to
            )
            .first()
        )

        if not assigned_user:
            raise HTTPException(
                status_code=404,
                detail="Assigned user not found",
            )

    task = Task(
        project_id=data.project_id,
        title=data.title,
        assigned_to=data.assigned_to,
        deadline=data.deadline,
        status="Pending",
    )

    db.add(task)
    db.commit()
    db.refresh(task)

    return {
        "message": "Task created successfully",
        "id": task.id,
    }


# ============================================================
# TASK STATUS UPDATE
# ============================================================


@app.patch("/api/tasks/{task_id}")
def update_task(
    task_id: int,
    data: TaskStatus,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    allowed_statuses = {
        "Pending",
        "In Progress",
        "Completed",
    }

    if data.status not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail=(
                "Status must be one of: "
                "Pending, In Progress, Completed"
            ),
        )

    task = (
        db.query(Task)
        .filter(Task.id == task_id)
        .first()
    )

    if not task:
        raise HTTPException(
            status_code=404,
            detail="Task not found",
        )

    project = (
        db.query(Project)
        .filter(
            Project.id
            == task.project_id
        )
        .first()
    )

    allowed = (
        user.role == "admin"
        or project.owner_id == user.id
        or task.assigned_to == user.id
    )

    if not allowed:
        raise HTTPException(
            status_code=403,
            detail="You cannot update this task",
        )

    task.status = data.status

    db.commit()
    db.refresh(task)

    return {
        "message": "Task updated successfully",
        "task": {
            "id": task.id,
            "title": task.title,
            "status": task.status,
        },
    }


# ============================================================
# STUDENT PROGRESS
# ============================================================


@app.get("/api/progress")
def get_progress(
    user: User = Depends(
        require_roles("student")
    ),
    db: Session = Depends(get_db),
):
    assignment_links = (
        db.query(AssignmentStudent)
        .filter(
            AssignmentStudent.student_id
            == user.id
        )
        .all()
    )

    assignment_ids = [
        x.assignment_id
        for x in assignment_links
    ]

    total_assignments = len(
        assignment_ids
    )

    submissions = (
        db.query(Submission)
        .filter(
            Submission.student_id
            == user.id
        )
        .all()
    )

    completed = len(
        [
            x for x in submissions
            if x.status in (
                "Submitted",
                "Late",
            )
        ]
    )

    assignment_progress = (
        round(
            completed
            / total_assignments
            * 100,
            1,
        )
        if total_assignments
        else 0
    )

    attendance_records = (
        db.query(Attendance)
        .filter(
            Attendance.student_id
            == user.id
        )
        .all()
    )

    present = len(
        [
            x for x in attendance_records
            if str(x.status).lower()
            == "present"
        ]
    )

    attendance_progress = (
        round(
            present
            / len(attendance_records)
            * 100,
            1,
        )
        if attendance_records
        else 0
    )

    marks = (
        db.query(Mark)
        .filter(
            Mark.student_id == user.id
        )
        .all()
    )

    marks_progress = (
        round(
            sum(x.marks for x in marks)
            / sum(
                x.max_marks
                for x in marks
            )
            * 100,
            1,
        )
        if marks
        and sum(
            x.max_marks
            for x in marks
        ) > 0
        else 0
    )

    overall = round(
        (
            assignment_progress
            + attendance_progress
            + marks_progress
        )
        / 3,
        1,
    )

    return {
        "assignment_progress": assignment_progress,
        "attendance_progress": attendance_progress,
        "marks_progress": marks_progress,
        "overall_progress": overall,
    }


# ============================================================
# NOTIFICATIONS
# Derived notifications from current academic data.
# No separate notification table is required.
# ============================================================


@app.get("/api/notifications")
def get_notifications(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notifications = []

    if user.role == "student":

        links = (
            db.query(AssignmentStudent)
            .filter(
                AssignmentStudent.student_id
                == user.id
            )
            .all()
        )

        assignment_ids = [
            x.assignment_id
            for x in links
        ]

        if assignment_ids:

            assignments = (
                db.query(Assignment)
                .filter(
                    Assignment.id.in_(
                        assignment_ids
                    )
                )
                .order_by(
                    Assignment.deadline.asc()
                )
                .all()
            )

            for assignment in assignments:

                submission = (
                    db.query(Submission)
                    .filter(
                        Submission.assignment_id
                        == assignment.id,
                        Submission.student_id
                        == user.id,
                    )
                    .first()
                )

                if not submission or (
                    submission.status
                    == "Not Submitted"
                ):

                    notifications.append(
                        {
                            "type": "assignment",
                            "title": "Assignment Pending",
                            "message": (
                                f"{assignment.title} "
                                f"is pending."
                            ),
                            "deadline": assignment.deadline,
                        }
                    )

        notices = (
            db.query(Notice)
            .order_by(
                Notice.created_at.desc()
            )
            .limit(5)
            .all()
        )

        for notice in notices:

            notifications.append(
                {
                    "type": "notice",
                    "title": notice.title,
                    "message": notice.message,
                    "created_at": notice.created_at,
                }
            )

    else:

        notices = (
            db.query(Notice)
            .order_by(
                Notice.created_at.desc()
            )
            .limit(10)
            .all()
        )

        for notice in notices:

            notifications.append(
                {
                    "type": "notice",
                    "title": notice.title,
                    "message": notice.message,
                    "created_at": notice.created_at,
                }
            )

    return notifications


# ============================================================
# CALENDAR DATA
# Combines assignments, timetable and projects.
# ============================================================


@app.get("/api/calendar")
def calendar(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    events = []

    # --------------------------------------------------------
    # ASSIGNMENTS
    # --------------------------------------------------------

    if user.role == "student":

        links = (
            db.query(AssignmentStudent)
            .filter(
                AssignmentStudent.student_id
                == user.id
            )
            .all()
        )

        ids = [
            x.assignment_id
            for x in links
        ]

        if ids:

            assignments = (
                db.query(Assignment)
                .filter(
                    Assignment.id.in_(ids)
                )
                .all()
            )

        else:
            assignments = []

    elif user.role == "faculty":

        assignments = (
            db.query(Assignment)
            .filter(
                Assignment.faculty_id
                == user.id
            )
            .all()
        )

    else:

        assignments = (
            db.query(Assignment)
            .all()
        )

    for assignment in assignments:

        events.append(
            {
                "type": "assignment",
                "id": assignment.id,
                "title": assignment.title,
                "subject": assignment.subject,
                "date": assignment.deadline,
                "deadline": assignment.deadline,
            }
        )

    # --------------------------------------------------------
    # TIMETABLE
    # --------------------------------------------------------

    timetable_rows = (
        db.query(Timetable)
        .all()
    )

    for row in timetable_rows:

        events.append(
            {
                "type": "class",
                "id": row.id,
                "title": row.subject,
                "day": row.day,
                "time": row.time,
                "faculty": row.faculty,
                "room": row.room,
            }
        )

    # --------------------------------------------------------
    # PROJECTS
    # --------------------------------------------------------

    if user.role == "admin":

        projects = (
            db.query(Project)
            .all()
        )

    else:

        projects = (
            db.query(Project)
            .filter(
                Project.owner_id == user.id
            )
            .all()
        )

    for project in projects:

        if project.deadline:

            events.append(
                {
                    "type": "project",
                    "id": project.id,
                    "title": project.name,
                    "date": project.deadline,
                    "status": project.status,
                }
            )

    return events


# ============================================================
# LATE DETECTION
# ============================================================


@app.get("/api/late-detection")
def late_detection(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role == "student":

        submissions = (
            db.query(Submission)
            .filter(
                Submission.student_id
                == user.id
            )
            .all()
        )

    elif user.role == "faculty":

        submissions = (
            db.query(Submission)
            .join(
                Assignment,
                Submission.assignment_id
                == Assignment.id,
            )
            .filter(
                Assignment.faculty_id
                == user.id
            )
            .all()
        )

    else:

        submissions = (
            db.query(Submission)
            .all()
        )

    result = []

    for submission in submissions:

        assignment = (
            db.query(Assignment)
            .filter(
                Assignment.id
                == submission.assignment_id
            )
            .first()
        )

        if not assignment:
            continue

        is_late = (
            submission.submitted_at is not None
            and submission.submitted_at
            > assignment.deadline
        )

        result.append(
            {
                "submission_id": submission.id,
                "assignment_id": assignment.id,
                "assignment": assignment.title,
                "student_id": submission.student_id,
                "deadline": assignment.deadline,
                "submitted_at": submission.submitted_at,
                "status": (
                    "Late"
                    if is_late
                    else submission.status
                ),
            }
        )

    return result


# ============================================================
# FACULTY - ALL STUDENTS
# ============================================================


@app.get("/api/students")
def get_students(
    search: Optional[str] = None,
    department: Optional[str] = None,
    user: User = Depends(
        require_roles("faculty", "admin")
    ),
    db: Session = Depends(get_db),
):
    query = (
        db.query(User)
        .filter(User.role == "student")
    )

    if search:

        pattern = f"%{search}%"

        query = query.filter(
            or_(
                User.name.ilike(pattern),
                User.email.ilike(pattern),
                User.student_id.ilike(pattern),
            )
        )

    if department:

        query = query.filter(
            User.department.ilike(
                f"%{department}%"
            )
        )

    students = (
        query
        .order_by(User.name.asc())
        .all()
    )

    return [
        user_dict(student)
        for student in students
    ]


# ============================================================
# FACULTY LIST
# ============================================================


@app.get("/api/faculty")
def get_faculty(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    faculty = (
        db.query(User)
        .filter(User.role == "faculty")
        .order_by(User.name.asc())
        .all()
    )

    return [
        user_dict(member)
        for member in faculty
    ]


# ============================================================
# SEARCH
# ============================================================


@app.get("/api/search")
def global_search(
    q: str = Query(
        min_length=1
    ),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pattern = f"%{q}%"

    assignments = (
        db.query(Assignment)
        .filter(
            or_(
                Assignment.title.ilike(pattern),
                Assignment.subject.ilike(pattern),
                Assignment.description.ilike(pattern),
            )
        )
        .limit(20)
        .all()
    )

    notices = (
        db.query(Notice)
        .filter(
            or_(
                Notice.title.ilike(pattern),
                Notice.message.ilike(pattern),
            )
        )
        .limit(20)
        .all()
    )

    projects = (
        db.query(Project)
        .filter(
            or_(
                Project.name.ilike(pattern),
                Project.description.ilike(pattern),
            )
        )
        .limit(20)
        .all()
    )

    return {
        "assignments": [
            {
                "id": x.id,
                "title": x.title,
                "subject": x.subject,
                "deadline": x.deadline,
            }
            for x in assignments
        ],
        "notices": [
            {
                "id": x.id,
                "title": x.title,
                "message": x.message,
                "created_at": x.created_at,
            }
            for x in notices
        ],
        "projects": [
            {
                "id": x.id,
                "name": x.name,
                "description": x.description,
                "deadline": x.deadline,
                "status": x.status,
            }
            for x in projects
        ],
    }


# ============================================================
# RESUBMISSION
# ============================================================
# Student can submit again before the deadline.
# The latest submission replaces the previous submission text.
# ============================================================


@app.post(
    "/api/assignments/{assignment_id}/resubmit"
)
def resubmit_assignment(
    assignment_id: int,
    data: AssignmentSubmit,
    user: User = Depends(
        require_roles("student")
    ),
    db: Session = Depends(get_db),
):
    assignment = (
        db.query(Assignment)
        .filter(
            Assignment.id == assignment_id
        )
        .first()
    )

    if not assignment:
        raise HTTPException(
            status_code=404,
            detail="Assignment not found",
        )

    assigned = (
        db.query(AssignmentStudent)
        .filter(
            AssignmentStudent.assignment_id
            == assignment_id,
            AssignmentStudent.student_id
            == user.id,
        )
        .first()
    )

    if not assigned:
        raise HTTPException(
            status_code=403,
            detail="Assignment not assigned to you",
        )

    now = datetime.utcnow()

    submission = (
        db.query(Submission)
        .filter(
            Submission.assignment_id
            == assignment_id,
            Submission.student_id
            == user.id,
        )
        .first()
    )

    if not submission:

        submission = Submission(
            assignment_id=assignment_id,
            student_id=user.id,
        )

        db.add(submission)

    submission.submission_text = (
        data.submission_text
    )

    submission.submitted_at = now

    if now > assignment.deadline:
        submission.status = "Late"
    else:
        submission.status = "Submitted"

    # Existing grading is cleared because
    # this is a new submission.
    submission.marks = None
    submission.feedback = None

    db.commit()
    db.refresh(submission)

    return {
        "message": "Assignment resubmitted successfully",
        "submission_id": submission.id,
        "submitted_at": submission.submitted_at,
        "status": submission.status,
    }


# ============================================================
# CURRENT USER PROFILE
# ============================================================


@app.get("/api/me")
def get_me(
    user: User = Depends(get_current_user),
):
    return user_dict(user)


# ============================================================
# STARTUP
# ============================================================


@app.on_event("startup")
def startup_event():
    print("=" * 60)
    print("CampusHUB Academic Portal API")
    print("Backend: FastAPI")
    print("Database: MySQL")
    print("CORS: localhost:5173 + 127.0.0.1:5173")
    print("=" * 60)
