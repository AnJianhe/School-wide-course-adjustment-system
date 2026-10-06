from extensions import db
import time
from werkzeug.security import generate_password_hash, check_password_hash

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    role = db.Column(db.String(10), nullable=False)  # 'teacher' or 'screen'
    password_hash = db.Column(db.String(256), nullable=False, default='')
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    must_change_password = db.Column(db.Boolean, nullable=False, default=True)
    session_version = db.Column(db.Integer, nullable=False, default=0)
    courses = db.relationship('Course', backref='teacher', lazy=True)
    
    def __repr__(self):
        return f'<User {self.username} ({self.role})>'

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return bool(self.password_hash) and check_password_hash(self.password_hash, password)

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    class_name = db.Column(db.String(10), nullable=False)  # 班级编号，如'101'
    time_slot = db.Column(db.String(20), nullable=False)  # 时间段，如'上午1'
    subject = db.Column(db.String(20), nullable=False)  # 课程名称
    teacher_id = db.Column(db.String(20), db.ForeignKey('user.username'), nullable=False)
    adjustments = db.relationship('AdjustmentRequest', backref='course', lazy=True)
    
    def __repr__(self):
        return f'<Course {self.class_name} {self.time_slot} {self.subject}>'

class AdjustmentRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    from_teacher_id = db.Column(db.String(20), db.ForeignKey('user.username'), nullable=False)
    to_teacher_id = db.Column(db.String(20), db.ForeignKey('user.username'), nullable=False)
    status = db.Column(db.String(20), default='pending')  # 'pending', 'approved', 'rejected'
    created_at = db.Column(db.Float, default=time.time)
    approved_at = db.Column(db.Float)
    reason = db.Column(db.String(500), nullable=False, default='')
    
    # 关联关系
    from_teacher = db.relationship('User', foreign_keys=[from_teacher_id])
    to_teacher = db.relationship('User', foreign_keys=[to_teacher_id])
    
    def to_dict(self):
        return {
            'id': self.id,
            'course_id': self.course_id,
            'from_teacher': self.from_teacher_id,
            'to_teacher': self.to_teacher_id,
            'status': self.status,
            'created_at': self.created_at,
            'approved_at': self.approved_at,
            'reason': self.reason,
            'class_name': self.course.class_name,
            'subject': self.course.subject,
            'time_slot': self.course.time_slot
        }
    
    def __repr__(self):
        return f'<AdjustmentRequest {self.id} {self.status}>'


class LoginAttempt(db.Model):
    key = db.Column(db.String(64), primary_key=True)
    failures = db.Column(db.Integer, nullable=False, default=0)
    started_at = db.Column(db.Float, nullable=False, default=time.time)
