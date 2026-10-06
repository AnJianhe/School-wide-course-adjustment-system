import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

from app import create_app
from extensions import db
from models import User, Course, AdjustmentRequest
from i18n import LANGUAGES, CATALOGS

PASSWORD = 'Test-only-Password42'


class SystemTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.uri = 'sqlite:///' + str(Path(self.temp.name) / 'test.db').replace('\\', '/')
        self.app = create_app({'TESTING': True, 'SECRET_KEY': 'test-key-' * 8,
                               'SQLALCHEMY_DATABASE_URI': self.uri})
        with self.app.app_context():
            for username, role in [('admin', 'admin'), ('t1', 'teacher'), ('t2', 'teacher'),
                                   ('t3', 'teacher'), ('101', 'screen'), ('102', 'screen')]:
                u = User(username=username, role=role, must_change_password=False)
                u.set_password(PASSWORD)
                db.session.add(u)
            db.session.flush()
            db.session.add_all([
                Course(id=1, class_name='101', time_slot='上午1', subject='语文', teacher_id='t1'),
                Course(id=2, class_name='102', time_slot='上午2', subject='数学', teacher_id='t2')])
            db.session.commit()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.temp.cleanup()

    def token(self, client):
        with client.session_transaction() as s:
            return s['csrf_token']

    def login(self, username, password=PASSWORD):
        client = self.app.test_client()
        client.get('/')
        response = client.post('/', data={'user_id': username, 'password': password,
                                          'csrf_token': self.token(client)})
        self.assertEqual(response.status_code, 302, response.data)
        return client

    def post(self, client, path, data=None, json=None, follow=False):
        kwargs = {'headers': {'X-CSRF-Token': self.token(client)}, 'follow_redirects': follow}
        kwargs['json' if json is not None else 'data'] = json if json is not None else data
        return client.post(path, **kwargs)

    def test_login_security_and_isolated_sessions(self):
        anonymous = self.app.test_client()
        anonymous.get('/')
        self.assertEqual(anonymous.get('/api/teacher/adjustments').status_code, 401)
        self.assertEqual(anonymous.post('/', data={'user_id': 't1', 'password': PASSWORD}).status_code, 400)
        self.assertEqual(anonymous.post('/', headers={'X-CSRF-Token': '中文'}, data={}).status_code, 400)
        for _ in range(10):
            self.assertEqual(self.post(anonymous, '/', data={'user_id': 't1', 'password': 'wrong'}).status_code, 401)
        self.assertEqual(self.post(anonymous, '/', data={'user_id': 't1', 'password': PASSWORD}).status_code, 429)
        one, two = self.login('t2'), self.login('t3')
        self.assertIn(b't2', one.get('/teacher/dashboard').data)
        self.assertIn(b't3', two.get('/teacher/dashboard').data)
        self.post(two, '/logout')
        self.assertEqual(one.get('/teacher/dashboard').status_code, 200)
        self.assertEqual(two.get('/teacher/dashboard').status_code, 302)
        screen = self.login('101')
        self.assertEqual(screen.get('/admin').status_code, 403)
        self.assertEqual(screen.get('/api/class/102/courses').status_code, 403)
        self.assertEqual(screen.get('/api/class/101/courses').status_code, 200)

    def test_adjustment_end_to_end_and_persistence(self):
        one, two, screen = self.login('t1'), self.login('t2'), self.login('101')
        created = self.post(one, '/api/adjustment/request', json={'course_id': 1,
                            'target_teacher_id': 't2', 'reason': '培训代课'})
        self.assertEqual(created.status_code, 200, created.data)
        rid = created.json['request_id']
        self.assertEqual(two.get('/api/teacher/adjustments').json['received'][0]['reason'], '培训代课')
        self.assertEqual(self.post(one, f'/api/adjustment/{rid}/handle', json={'action': 'approve'}).status_code, 403)
        self.assertEqual(self.post(two, f'/api/adjustment/{rid}/handle', json={'action': 'invalid'}).status_code, 400)
        approved = self.post(two, f'/api/adjustment/{rid}/handle', json={'action': 'approve'})
        self.assertEqual(approved.status_code, 200, approved.data)
        result = screen.get('/api/class/101/courses').json[0]
        self.assertEqual(result['current_teacher'], 't2')
        self.assertIsNotNone(result['adjustment']['approved_at'])
        self.assertEqual(self.post(two, f'/api/adjustment/{rid}/handle', json={'action': 'approve'}).status_code, 409)
        self.assertNotIn('语文'.encode(), one.get('/teacher/dashboard').data)
        self.assertIn('语文'.encode(), two.get('/teacher/dashboard').data)
        restarted = create_app({'TESTING': True, 'SECRET_KEY': 'test-key-' * 8,
                                'SQLALCHEMY_DATABASE_URI': self.uri})
        with restarted.app_context():
            self.assertEqual(db.session.get(AdjustmentRequest, rid).status, 'approved')
            db.session.remove()
            db.engine.dispose()

    def test_input_ownership_duplicate_and_conflict(self):
        one, two = self.login('t1'), self.login('t2')
        self.assertEqual(self.post(one, '/api/adjustment/request', json=[]).status_code, 400)
        self.assertEqual(self.post(one, '/api/adjustment/request', json={'course_id': True}).status_code, 400)
        self.assertEqual(self.post(one, '/api/adjustment/request', json={'course_id': 2, 'target_teacher_id': 't3'}).status_code, 403)
        self.assertEqual(self.post(one, '/api/adjustment/request', json={'course_id': 1, 'target_teacher_id': 't1'}).status_code, 400)
        self.assertEqual(self.post(one, '/api/adjustment/request', json={'course_id': 1, 'target_teacher_id': 't3', 'reason': 1}).status_code, 400)
        good = {'course_id': 1, 'target_teacher_id': 't3'}
        self.assertEqual(self.post(one, '/api/adjustment/request', json=good).status_code, 200)
        self.assertEqual(self.post(one, '/api/adjustment/request', json=good).status_code, 409)
        self.assertEqual(self.post(two, '/api/adjustment/1/handle', json={'action': 'reject'}).status_code, 403)
        three = self.login('t3')
        self.assertEqual(self.post(three, '/api/adjustment/1/handle', json={'action': 'reject'}).status_code, 200)
        with self.app.app_context():
            db.session.add(Course(class_name='102', time_slot='上午1', subject='体育', teacher_id='t3'))
            db.session.commit()
        self.assertEqual(self.post(one, '/api/adjustment/request', json=good).status_code, 409)

    def test_concurrent_approvals_recheck_conflict(self):
        with self.app.app_context():
            db.session.get(Course, 2).time_slot = '上午1'
            db.session.add_all([AdjustmentRequest(course_id=1, from_teacher_id='t1', to_teacher_id='t3'),
                                AdjustmentRequest(course_id=2, from_teacher_id='t2', to_teacher_id='t3')])
            db.session.commit()
        clients = [self.login('t3'), self.login('t3')]
        def approve(pair):
            client, rid = pair
            return self.post(client, f'/api/adjustment/{rid}/handle', json={'action': 'approve'}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(approve, zip(clients, [1, 2])))
        self.assertEqual(sorted(statuses), [200, 409])

    def test_admin_password_reset_disable_and_last_admin(self):
        admin, teacher = self.login('admin'), self.login('t1')
        response = self.post(admin, '/admin/users', data={'username': 'new', 'role': 'teacher',
                             'password': 'Initial-Password42', 'enabled': 'on'}, follow=True)
        self.assertEqual(response.status_code, 200, response.data)
        fresh = self.login('new', 'Initial-Password42')
        self.assertEqual(fresh.get('/api/teacher/adjustments').status_code, 403)
        bad = self.post(fresh, '/account/password', data={'old_password': 'wrong', 'new_password': PASSWORD, 'confirm_password': PASSWORD})
        self.assertEqual(bad.status_code, 400)
        good = self.post(fresh, '/account/password', data={'old_password': 'Initial-Password42', 'new_password': PASSWORD, 'confirm_password': PASSWORD})
        self.assertEqual(good.status_code, 302)
        self.assertEqual(fresh.get('/teacher/dashboard').status_code, 200)
        self.post(admin, '/admin/users', data={'username': 't1', 'role': 'teacher', 'password': PASSWORD + 'x', 'enabled': 'on'})
        self.assertEqual(teacher.get('/api/teacher/adjustments').status_code, 401)
        reset = self.login('t1', PASSWORD + 'x')
        self.assertEqual(reset.get('/teacher/dashboard').location, '/account/password')
        self.post(admin, '/admin/users', data={'username': 't1', 'role': 'teacher'})
        self.assertEqual(reset.get('/api/teacher/adjustments').status_code, 401)
        self.post(admin, '/admin/users', data={'username': 'admin', 'role': 'teacher'})
        with self.app.app_context():
            self.assertEqual(User.query.filter_by(username='admin').first().role, 'admin')
            self.assertTrue(User.query.filter_by(username='admin').first().enabled)
            self.assertNotEqual(User.query.filter_by(username='new').first().password_hash, PASSWORD)

    def test_admin_course_management_and_xss_escape(self):
        admin = self.login('admin')
        course = {'class_name': '101', 'time_slot': '下午1', 'subject': '<script>x</script>', 'teacher_id': 't3'}
        self.post(admin, '/admin/courses', data=course)
        response = admin.get('/admin')
        self.assertIn(b'&lt;script&gt;x&lt;/script&gt;', response.data)
        self.assertNotIn(b'<script>x</script>', response.data)
        with self.app.app_context():
            self.assertEqual(Course.query.count(), 3)
        self.post(admin, '/admin/courses', data=course)  # 班级重复
        course.update(class_name='102')
        self.post(admin, '/admin/courses', data=course)  # 教师重复
        with self.app.app_context():
            self.assertEqual(Course.query.count(), 3)
        self.post(admin, '/admin/courses', data={'course_id': 3, 'class_name': '101',
                  'time_slot': '下午2', 'subject': '科学', 'teacher_id': 't3'})
        self.post(admin, '/admin/courses/3/delete')
        with self.app.app_context():
            self.assertEqual(Course.query.count(), 2)
        teacher = self.login('t1')
        self.assertEqual(self.post(teacher, '/admin/courses', data=course).status_code, 403)

    def test_cli_demo_and_password_recovery(self):
        runner = self.app.test_cli_runner()
        self.assertEqual(runner.invoke(args=['create-admin', '--username', 'admin2', '--password', PASSWORD]).exit_code, 0)
        self.assertNotEqual(runner.invoke(args=['create-admin', '--username', 'admin2', '--password', PASSWORD]).exit_code, 0)
        self.assertNotEqual(runner.invoke(args=['seed-demo']).exit_code, 0)
        self.assertEqual(runner.invoke(args=['reset-password', '--username', 't1', '--password', PASSWORD + 'new']).exit_code, 0)

    def test_legacy_migration_is_backed_up_and_idempotent(self):
        target = Path(self.temp.name) / 'legacy.db'
        with closing(sqlite3.connect(target)) as conn:
            conn.executescript('''
            CREATE TABLE user (id INTEGER PRIMARY KEY, username VARCHAR(20) UNIQUE NOT NULL, role VARCHAR(10) NOT NULL);
            CREATE TABLE course (id INTEGER PRIMARY KEY, class_name VARCHAR(10) NOT NULL, time_slot VARCHAR(20) NOT NULL, subject VARCHAR(20) NOT NULL, teacher_id VARCHAR(20) NOT NULL);
            CREATE TABLE adjustment_request (id INTEGER PRIMARY KEY, course_id INTEGER NOT NULL, from_teacher_id VARCHAR(20) NOT NULL, to_teacher_id VARCHAR(20) NOT NULL, status VARCHAR(20), created_at FLOAT, approved_at FLOAT);
            INSERT INTO user VALUES(1,'old','teacher');
            INSERT INTO course VALUES(1,'101','上午1','语文','old');
            ''')
        for _ in range(2):
            migrated = create_app({'TESTING': True, 'SECRET_KEY': 'legacy-test-' * 4,
                                  'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + target.as_posix()})
            with migrated.app_context():
                self.assertEqual(User.query.count(), 1)
                self.assertEqual(Course.query.count(), 1)
                self.assertFalse(User.query.first().check_password(''))
                self.assertTrue(User.query.first().must_change_password)
                db.session.remove()
                db.engine.dispose()
        self.assertTrue(target.with_name('legacy.db.pre-auth.bak').exists())
        with closing(sqlite3.connect(target.with_name('legacy.db.pre-auth.bak'))) as conn:
            self.assertEqual(len(conn.execute('PRAGMA table_info(user)').fetchall()), 3)

    def test_twenty_languages_auto_detection_and_manual_preference(self):
        self.assertEqual(len(LANGUAGES), 20)
        expected_keys = set(CATALOGS['zh-CN'])
        self.assertGreater(len(expected_keys), 150)
        for language in LANGUAGES:
            self.assertEqual(set(CATALOGS[language]), expected_keys)
            self.assertTrue(all(CATALOGS[language].values()))
            client = self.app.test_client()
            response = client.get('/', headers={'Accept-Language': language})
            self.assertEqual(response.status_code, 200)
            self.assertIn(f'lang="{language}"'.encode(), response.data)
            self.assertIn(('dir="rtl"' if language == 'ar' else 'dir="ltr"').encode(), response.data)
        client = self.app.test_client()
        for preference, result in [('en-US,en;q=0.9','en'), ('ja-JP','ja'), ('ko-KR','ko'),
                                   ('zh-Hant','zh-TW'), ('zh-HK','zh-TW'), ('fr-CA','fr'),
                                   ('xx-XX','zh-CN'), ('en;q=0.2,ja;q=0.9','ja')]:
            response = client.get('/', headers={'Accept-Language': preference})
            self.assertIn(f'lang="{result}"'.encode(), response.data)
        client.get('/')
        self.post(client, '/language', data={'language':'ar','next':'https://example.com'})
        self.assertIn(b'lang="ar"', client.get('/', headers={'Accept-Language':'en'}).data)
        self.assertEqual(self.post(client, '/language', data={'language':'invalid'}).status_code, 400)
        response = self.post(client, '/language', data={'language':'ja','next':'//example.com'})
        self.assertEqual(response.location, '/')
        response = self.post(client, '/api/adjustment/request', json={})
        self.assertEqual(response.json['message'], CATALOGS['ja']['请先登录'])

    def test_localized_admin_teacher_and_screen_pages(self):
        clients = [(self.login('admin'), '/admin'), (self.login('t1'), '/teacher/dashboard'),
                   (self.login('101'), '/screen/101')]
        for client, path in clients:
            for locale in LANGUAGES:
                response = self.post(client, '/language', data={'language':locale,'next':path})
                self.assertEqual(response.status_code, 302)
                response = client.get(path)
                self.assertEqual(response.status_code, 200, response.data)
                self.assertIn(f'lang="{locale}"'.encode(), response.data)
                self.assertIn('id="translations"'.encode(), response.data)
                if path == '/admin':
                    self.assertIn('value="上午1"'.encode(), response.data)


if __name__ == '__main__':
    unittest.main()
