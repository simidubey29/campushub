from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class Login(BaseModel):
    email: str
    password: str

class StudentRegister(BaseModel):
    name: str
    email: str
    password: str
    student_id: str
    department: Optional[str] = None
    semester: Optional[str] = None

class AdminUserCreate(BaseModel):
    name: str
    email: str
    password: str
    role: str
    student_id: Optional[str] = None
    department: Optional[str] = None
    semester: Optional[str] = None

class AssignmentCreate(BaseModel):
    title: str
    description: Optional[str] = None
    subject: str
    deadline: datetime
    student_ids: list[int] = Field(default_factory=list)
    max_marks: float = 100
    allow_resubmission: bool = True
    max_resubmissions: int = 2

class AssignmentSubmit(BaseModel):
    submission_text: str

class GradeSubmission(BaseModel):
    marks: float
    feedback: Optional[str] = None

class MarkCreate(BaseModel):
    student_id: int
    subject: str
    exam: str
    marks: float
    max_marks: float = 100

class AttendanceCreate(BaseModel):
    student_id: int
    subject: str
    attendance_date: str
    status: str

class NoticeCreate(BaseModel):
    title: str
    message: str

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    deadline: Optional[datetime] = None

class TaskCreate(BaseModel):
    project_id: int
    title: str
    assigned_to: Optional[int] = None
    deadline: Optional[datetime] = None

class TaskStatus(BaseModel):
    status: str

class NotificationRead(BaseModel):
    is_read: bool = True
