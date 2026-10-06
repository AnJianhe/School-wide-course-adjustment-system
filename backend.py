import hashlib
import os
import re
import secrets
import shutil
import time
from datetime import timedelta
from functools import wraps
from contextlib import closing
from pathlib import Path

import click
from dotenv import load_dotenv
from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy import event, inspect, text
from sqlalchemy.exc import IntegrityError, OperationalError
from extensions import db
from models import User, Course, AdjustmentRequest, LoginAttempt
from i18n import LANGUAGES, CATALOGS, detect_language, translate as _

ROOT = Path(__file__).resolve().parent
TIME_SLOTS = ('上午1', '上午2', '下午1', '下午2')
ROLES = ('admin', 'teacher', 'screen')


def error(message, code=400):
    return jsonify(status='error', message=_(message)), code


def valid_password(value):
    return isinstance(value, str) and 10 <= len(value) <= 128


def require_role(*roles):
    def decorate(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not g.user:
                return error('请先登录', 401) if request.path.startswith('/api/') else redirect(url_for('login'))
            if g.user.must_change_password:
                return error('请先修改初始密码', 403) if request.path.startswith('/api/') else redirect(url_for('password'))
            if roles and g.user.role not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorate


def active_teacher(course):
    latest = AdjustmentRequest.query.filter_by(course_id=course.id, status='approved').order_by(
        AdjustmentRequest.approved_at.desc(), AdjustmentRequest.id.desc()).first()
    return (latest.to_teacher_id if latest else course.teacher_id), latest


def teacher_busy(teacher_id, slot, exclude=None):
    return any(active_teacher(c)[0] == teacher_id for c in
               Course.query.filter(Course.time_slot == slot, Course.id != exclude).all())


def initialize_database():
    """保留旧库数据；添加认证字段前，保留一次完整 SQLite 备份。"""
    engine = db.engine
    if engine.dialect.name != 'sqlite':
        raise RuntimeError('本版本使用 SQLite，请配置 sqlite:/// 数据库地址')
    additions = {
        'user': {'password_hash': "VARCHAR(256) NOT NULL DEFAULT ''",
                 'enabled': 'BOOLEAN NOT NULL DEFAULT 1',
                 'must_change_password': 'BOOLEAN NOT NULL DEFAULT 1',
                 'session_version': 'INTEGER NOT NULL DEFAULT 0'},
        'adjustment_request': {'reason': "VARCHAR(500) NOT NULL DEFAULT ''"},
    }
    tables = inspect(engine).get_table_names()
    changes = [(table, col, definition) for table, columns in additions.items() if table in tables
               for col, definition in columns.items()
               if col not in {c['name'] for c in inspect(engine).get_columns(table)}]
    if changes and engine.url.database != ':memory:':
        import sqlite3
        target = Path(engine.url.database)
        backup = target.with_name(target.name + '.pre-auth.bak')
        if not backup.exists():
            with closing(sqlite3.connect(target)) as source, closing(sqlite3.connect(backup)) as dest:
                source.backup(dest)
    with engine.begin() as connection:
        for table, col, definition in changes:
            connection.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{col}" {definition}'))
    db.create_all()


def create_app(test_config=None):
    app = Flask(__name__, instance_path=str(ROOT / 'instance'))
    load_dotenv(ROOT / '.env')
    app.config.update(SQLALCHEMY_DATABASE_URI=os.getenv('DATABASE_URI', 'sqlite:///school.db'),
                      SQLALCHEMY_TRACK_MODIFICATIONS=False, SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE', '0') == '1',
                      PERMANENT_SESSION_LIFETIME=timedelta(hours=8), MAX_CONTENT_LENGTH=64 * 1024)
    if test_config:
        app.config.update(test_config)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    secret = app.config.get('SECRET_KEY') or os.getenv('SECRET_KEY')
    if not secret:
        secret_file = Path(app.instance_path) / 'secret.key'
        try:
            with secret_file.open('x', encoding='utf-8') as f:
                f.write(secrets.token_hex(32))
        except FileExistsError:
            pass
        secret = secret_file.read_text(encoding='utf-8').strip()
    if len(secret) < 32:
        raise RuntimeError('SECRET_KEY 至少需要 32 个字符，请更换旧配置')
    app.config['SECRET_KEY'] = secret
    uri = app.config['SQLALCHEMY_DATABASE_URI']
    if uri.startswith('sqlite:///') and not uri.startswith('sqlite:////'):
        filename = uri[len('sqlite:///'):]
        if filename != ':memory:' and not Path(filename).is_absolute():
            legacy, target = ROOT / filename, Path(app.instance_path) / filename
            if legacy.exists() and not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(legacy, target)
    db.init_app(app)
    with app.app_context():
        @event.listens_for(db.engine, 'connect')
        def sqlite_settings(connection, _):
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA busy_timeout=10000')
        initialize_database()

    @app.before_request
    def authentication_and_csrf():
        g.locale = detect_language()
        # SQLite 写操作串行，避免同时批准导致同一教师占用两节课。
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            db.session.execute(text('BEGIN IMMEDIATE'))
        g.user = db.session.get(User, session.get('user_id')) if session.get('user_id') else None
        if g.user and (not g.user.enabled or session.get('version') != g.user.session_version):
            session.clear()
            g.user = None
        session.setdefault('csrf_token', secrets.token_urlsafe(32))
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            token = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token', '')
            if not secrets.compare_digest(token.encode('utf-8'), session['csrf_token'].encode('utf-8')):
                return error('页面已过期，请刷新后重试')

    @app.context_processor
    def template_context():
        return dict(current_user=g.user, csrf_token=session.get('csrf_token'), time_slots=TIME_SLOTS,
                    _=_, languages=LANGUAGES, locale=g.locale, messages=CATALOGS[g.locale])

    @app.post('/language')
    def set_language():
        locale = request.form.get('language')
        if locale not in LANGUAGES:
            return error('语言无效')
        destination = request.form.get('next', '/')
        from urllib.parse import urlsplit
        parsed = urlsplit(destination)
        if not destination.startswith('/') or destination.startswith('//') or parsed.netloc or parsed.scheme or '\\' in destination:
            destination = '/'
        response = redirect(destination)
        response.set_cookie('language', locale, max_age=31536000, httponly=True,
                            secure=app.config['SESSION_COOKIE_SECURE'], samesite='Lax')
        return response

    @app.after_request
    def response_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        if request.endpoint != 'static':
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.errorhandler(403)
    def forbidden(exc):
        return error('无权访问', 403) if request.path.startswith('/api/') else (_('无权访问'), 403)

    @app.errorhandler(IntegrityError)
    def integrity_error(exc):
        db.session.rollback()
        return error('数据重复或关联无效，请刷新后重试', 409)

    @app.errorhandler(OperationalError)
    def database_error(exc):
        db.session.rollback()
        app.logger.exception('Database operation failed')
        return error('数据库暂时忙碌，请稍后重试', 503)

    def home():
        if g.user.must_change_password:
            return redirect(url_for('password'))
        if g.user.role == 'admin':
            return redirect(url_for('admin'))
        if g.user.role == 'teacher':
            return redirect(url_for('teacher_dashboard'))
        return redirect(url_for('screen_display', class_id=g.user.username))

    @app.route('/', methods=['GET', 'POST'])
    def login():
        if request.method == 'GET' and g.user:
            return home()
        message, status = None, 200
        if request.method == 'POST':
            username = request.form.get('user_id', '').strip()
            supplied = request.form.get('password', '')
            key = hashlib.sha256(((request.remote_addr or '') + ':' + username).encode()).hexdigest()
            attempt = db.session.get(LoginAttempt, key)
            now = time.time()
            if attempt and attempt.failures >= 10 and now - attempt.started_at < 600:
                message, status = '登录尝试过多，请 10 分钟后再试', 429
            else:
                user = User.query.filter_by(username=username).first()
                if user and user.enabled and len(supplied) <= 128 and user.check_password(supplied):
                    if attempt:
                        db.session.delete(attempt)
                        db.session.commit()
                    session.clear()
                    session.update(user_id=user.id, version=user.session_version, csrf_token=secrets.token_urlsafe(32))
                    session.permanent = True
                    g.user = user
                    return home()
                if not attempt:
                    attempt = LoginAttempt(key=key, failures=0, started_at=now)
                    db.session.add(attempt)
                if now - attempt.started_at >= 600:
                    attempt.failures, attempt.started_at = 0, now
                attempt.failures += 1
                LoginAttempt.query.filter(LoginAttempt.started_at < now - 86400).delete()
                db.session.commit()
                message, status = '账号或密码错误，或账号已停用', 401
        configured = User.query.filter_by(role='admin', enabled=True).count() > 0
        return render_template('login.html', error=message, configured=configured), status

    @app.post('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login'))

    @app.route('/account/password', methods=['GET', 'POST'])
    def password():
        if not g.user:
            return redirect(url_for('login'))
        message = None
        if request.method == 'POST':
            old, new = request.form.get('old_password', ''), request.form.get('new_password', '')
            if len(old) > 128 or not g.user.check_password(old):
                message = '当前密码不正确'
            elif not valid_password(new):
                message = '新密码长度须为 10～128 个字符'
            elif new != request.form.get('confirm_password'):
                message = '两次输入的新密码不一致'
            elif g.user.check_password(new):
                message = '新密码须与当前密码不同'
            else:
                g.user.set_password(new)
                g.user.must_change_password = False
                g.user.session_version += 1
                db.session.commit()
                session['version'] = g.user.session_version
                flash(_('密码已修改，其他登录会话已退出'))
                return home()
        return render_template('password.html', error=message), 400 if message else 200

    @app.get('/teacher/dashboard')
    @require_role('teacher')
    def teacher_dashboard():
        courses = [c for c in Course.query.all() if active_teacher(c)[0] == g.user.username]
        others = User.query.filter(User.role == 'teacher', User.enabled.is_(True),
                                  User.username != g.user.username, User.password_hash != '').all()
        return render_template('teacher_dashboard.html', courses=courses, other_teachers=others)

    def class_allowed(class_id):
        if not User.query.filter_by(username=class_id, role='screen', enabled=True).first():
            abort(404)
        if g.user.role == 'screen' and g.user.username != class_id:
            abort(403)

    @app.get('/screen/<class_id>')
    @require_role('screen', 'teacher', 'admin')
    def screen_display(class_id):
        class_allowed(class_id)
        return render_template('screen_display.html', class_id=class_id)

    @app.get('/api/class/<class_id>/courses')
    @require_role('screen', 'teacher', 'admin')
    def get_class_courses(class_id):
        class_allowed(class_id)
        result = []
        for c in Course.query.filter_by(class_name=class_id).all():
            teacher, latest = active_teacher(c)
            result.append(dict(id=c.id, time_slot=c.time_slot, subject=c.subject,
                               original_teacher=c.teacher_id, current_teacher=teacher,
                               adjustment=latest.to_dict() if latest else None))
        return jsonify(result)

    @app.post('/api/adjustment/request')
    @require_role('teacher')
    def submit_adjustment():
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or type(data.get('course_id')) is not int:
            return error('请提供有效的课程编号')
        course = db.session.get(Course, data['course_id'])
        if not course or active_teacher(course)[0] != g.user.username:
            return error('课程不存在或无权操作', 403)
        target_id = data.get('target_teacher_id')
        if not isinstance(target_id, str) or target_id == g.user.username:
            return error('请选择其他教师')
        target = User.query.filter_by(username=target_id, role='teacher', enabled=True).first()
        if not target or not target.password_hash:
            return error('目标教师不存在、已停用或尚未配置密码')
        reason = data.get('reason', '')
        if not isinstance(reason, str) or len(reason) > 500:
            return error('调课原因不得超过 500 个字符')
        if AdjustmentRequest.query.filter_by(course_id=course.id, status='pending').first():
            return error('该课程已有待处理申请', 409)
        if teacher_busy(target_id, course.time_slot, course.id):
            return error('目标教师在该时间段已有课程', 409)
        adjustment = AdjustmentRequest(course_id=course.id, from_teacher_id=g.user.username,
                                       to_teacher_id=target_id, reason=reason.strip(), status='pending')
        db.session.add(adjustment)
        db.session.commit()
        return jsonify(status='success', message=_('调课申请已提交'), request_id=adjustment.id)

    @app.get('/api/teacher/adjustments')
    @require_role('teacher')
    def get_teacher_adjustments():
        received = AdjustmentRequest.query.filter_by(to_teacher_id=g.user.username).order_by(AdjustmentRequest.id.desc()).all()
        sent = AdjustmentRequest.query.filter_by(from_teacher_id=g.user.username).order_by(AdjustmentRequest.id.desc()).all()
        return jsonify(received=[r.to_dict() for r in received], sent=[r.to_dict() for r in sent])

    @app.post('/api/adjustment/<int:request_id>/handle')
    @require_role('teacher')
    def handle_adjustment(request_id):
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or data.get('action') not in ('approve', 'reject'):
            return error('操作须为 approve 或 reject')
        adjustment = db.session.get(AdjustmentRequest, request_id)
        if not adjustment or adjustment.to_teacher_id != g.user.username:
            return error('申请不存在或无权操作', 403)
        if adjustment.status != 'pending':
            return error('申请已处理', 409)
        if data['action'] == 'approve':
            if active_teacher(adjustment.course)[0] != adjustment.from_teacher_id:
                return error('课程任课教师已变化，请拒绝此申请', 409)
            if not adjustment.from_teacher.enabled or adjustment.from_teacher.role != 'teacher':
                return error('申请人已停用，请拒绝此申请', 409)
            if teacher_busy(g.user.username, adjustment.course.time_slot, adjustment.course_id):
                return error('该时间段已有课程，无法批准', 409)
            adjustment.status, adjustment.approved_at = 'approved', time.time()
        else:
            adjustment.status, adjustment.approved_at = 'rejected', None
        db.session.commit()
        return jsonify(status='success', message=_('申请已批准' if adjustment.status == 'approved' else '申请已拒绝'))

    @app.get('/admin')
    @require_role('admin')
    def admin():
        return render_template('admin.html', users=User.query.order_by(User.role, User.username).all(),
                               courses=Course.query.order_by(Course.class_name, Course.id).all(),
                               adjustments=AdjustmentRequest.query.order_by(AdjustmentRequest.id.desc()).all())

    @app.post('/admin/users')
    @require_role('admin')
    def save_user():
        username, role = request.form.get('username', '').strip(), request.form.get('role')
        value, enabled = request.form.get('password', ''), request.form.get('enabled') == 'on'
        user = User.query.filter_by(username=username).first()
        message = None
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,20}', username) or role not in ROLES:
            message = '账号须为 1～20 位字母、数字、下划线或短横线，角色须有效'
        elif (not user and not valid_password(value)) or (value and not valid_password(value)):
            message = '创建账号或重置密码时，密码须为 10～128 个字符'
        elif user and user.role == 'admin' and (role != 'admin' or not enabled) and (
                user.id == g.user.id or User.query.filter_by(role='admin', enabled=True).count() <= 1):
            message = '不能停用或降级当前管理员及最后一个管理员'
        elif user and role != user.role and (
                Course.query.filter((Course.teacher_id == username) | (Course.class_name == username)).first() or
                AdjustmentRequest.query.filter((AdjustmentRequest.from_teacher_id == username) |
                                               (AdjustmentRequest.to_teacher_id == username)).first()):
            message = '该账号有关联课表或申请，不能变更角色；可停用账号'
        if message:
            flash(_(message), 'error')
            return redirect(url_for('admin'))
        if not user:
            user = User(username=username, role=role, session_version=0)
            db.session.add(user)
        else:
            user.session_version += 1
        user.role, user.enabled = role, enabled
        if value:
            user.set_password(value)
            user.must_change_password = True
        db.session.commit()
        if user.id == g.user.id:
            session['version'] = user.session_version
        flash(_('账号已保存；重置密码后，用户下次登录须修改密码'))
        return redirect(url_for('admin'))

    @app.post('/admin/courses')
    @require_role('admin')
    def save_course():
        class_id, teacher_id = request.form.get('class_name', '').strip(), request.form.get('teacher_id', '').strip()
        slot, subject = request.form.get('time_slot'), request.form.get('subject', '').strip()
        course_id = request.form.get('course_id', '')
        course = db.session.get(Course, int(course_id)) if course_id.isdigit() else None
        message = None
        if course_id and not course:
            message = '课程不存在'
        elif not User.query.filter_by(username=class_id, role='screen', enabled=True).first():
            message = '请先创建或启用班级账号'
        elif not User.query.filter_by(username=teacher_id, role='teacher', enabled=True).first():
            message = '请选择已启用的教师账号'
        elif slot not in TIME_SLOTS or not 1 <= len(subject) <= 20:
            message = '时间段无效或课程名称须为 1～20 个字符'
        elif course and AdjustmentRequest.query.filter_by(course_id=course.id).first():
            message = '课程已有关联调课记录，不能修改其基础课表'
        elif Course.query.filter(Course.class_name == class_id, Course.time_slot == slot,
                                 Course.id != (course.id if course else None)).first():
            message = '班级在该时间段已有课程'
        elif teacher_busy(teacher_id, slot, course.id if course else None):
            message = '教师在该时间段已有课程'
        if message:
            flash(_(message), 'error')
        else:
            if not course:
                course = Course()
                db.session.add(course)
            course.class_name, course.teacher_id, course.time_slot, course.subject = class_id, teacher_id, slot, subject
            db.session.commit()
            flash(_('课程已保存'))
        return redirect(url_for('admin'))

    @app.post('/admin/courses/<int:course_id>/delete')
    @require_role('admin')
    def delete_course(course_id):
        course = db.session.get(Course, course_id)
        if not course:
            abort(404)
        if course.adjustments:
            flash(_('课程有关联调课记录，不能删除'), 'error')
        else:
            db.session.delete(course)
            db.session.commit()
            flash(_('课程已删除'))
        return redirect(url_for('admin'))

    @app.cli.command('create-admin')
    @click.option('--username', prompt='管理员账号')
    @click.option('--password', prompt='管理员密码', hide_input=True, confirmation_prompt=True)
    def create_admin(username, password):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,20}', username) or not valid_password(password):
            raise click.ClickException('账号格式无效或密码长度不在 10～128 个字符之间')
        if User.query.filter_by(username=username).first():
            raise click.ClickException('账号已存在，请使用其他账号')
        user = User(username=username, role='admin', enabled=True, must_change_password=False)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo('管理员已创建')

    @app.cli.command('reset-password')
    @click.option('--username', prompt='账号')
    @click.option('--password', prompt='新密码', hide_input=True, confirmation_prompt=True)
    def reset_password(username, password):
        user = User.query.filter_by(username=username).first()
        if not user or not valid_password(password):
            raise click.ClickException('账号不存在或密码长度不在 10～128 个字符之间')
        user.set_password(password)
        user.must_change_password = True
        user.session_version += 1
        db.session.commit()
        click.echo('密码已重置，旧会话已失效')

    @app.cli.command('seed-demo')
    def demo():
        if User.query.filter(User.role != 'admin').count() or Course.query.count():
            raise click.ClickException('已有业务数据，未写入演示数据')
        from seed import seed_demo
        seed_demo()
        click.echo('演示课表已创建；教师和班级账号需由管理员配置密码')

    return app
