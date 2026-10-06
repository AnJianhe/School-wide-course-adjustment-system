from extensions import db
from models import User, Course

def seed_demo():
    # 显式初始化演示数据，不给用户设置公共密码

    if User.query.filter(User.role != 'admin').count() == 0:
        # 创建教师用户
        for i in range(1, 37):
            teacher_id = f'qfc{i:02d}'
            user = User(username=teacher_id, role='teacher')
            db.session.add(user)
        
        # 创建班级大屏用户
        for grade in range(1, 7):
            for class_num in range(1, 6):
                class_id = f'{grade}{class_num:02d}'
                user = User(username=class_id, role='screen')
                db.session.add(user)
        
        # 提交用户数据
        db.session.commit()

        # 初始化课程数据
        # 一年级课程
        grade1_classes = ['101', '102', '103', '104', '105']
        grade1_courses = [
            ['上午1', ['YuWen(qfc01)', 'ShuXue(qfc02)', 'YingYu(qfc03)', 'TiYu(qfc04)', 'MeiShu(qfc05)']],
            ['上午2', ['ShuXue(qfc02)', 'YuWen(qfc01)', 'TiYu(qfc04)', 'YingYu(qfc03)', 'YinYue(qfc06)']],
            ['下午1', ['YingYu(qfc03)', 'MeiShu(qfc05)', 'ShuXue(qfc02)', 'YinYue(qfc06)', 'YuWen(qfc01)']],
            ['下午2', ['TiYu(qfc04)', 'YinYue(qfc06)', 'MeiShu(qfc05)', 'YuWen(qfc01)', 'ShuXue(qfc02)']]
        ]
        
        # 二年级课程
        grade2_classes = ['201', '202', '203', '204', '205']
        grade2_courses = [
            ['上午1', ['YuWen(qfc07)', 'ShuXue(qfc08)', 'YingYu(qfc09)', 'TiYu(qfc10)', 'MeiShu(qfc11)']],
            ['上午2', ['ShuXue(qfc08)', 'YuWen(qfc07)', 'TiYu(qfc10)', 'YingYu(qfc09)', 'YinYue(qfc12)']],
            ['下午1', ['YingYu(qfc09)', 'MeiShu(qfc11)', 'ShuXue(qfc08)', 'YinYue(qfc12)', 'YuWen(qfc07)']],
            ['下午2', ['TiYu(qfc10)', 'YinYue(qfc12)', 'MeiShu(qfc11)', 'YuWen(qfc07)', 'ShuXue(qfc08)']]
        ]
        
        # 三年级课程
        grade3_classes = ['301', '302', '303', '304', '305']
        grade3_courses = [
            ['上午1', ['YuWen(qfc13)', 'ShuXue(qfc14)', 'YingYu(qfc15)', 'TiYu(qfc16)', 'KeXue(qfc17)']],
            ['上午2', ['ShuXue(qfc14)', 'YuWen(qfc13)', 'TiYu(qfc16)', 'KeXue(qfc17)', 'YinYue(qfc18)']],
            ['下午1', ['YingYu(qfc15)', 'KeXue(qfc17)', 'ShuXue(qfc14)', 'YinYue(qfc18)', 'YuWen(qfc13)']],
            ['下午2', ['TiYu(qfc16)', 'YinYue(qfc18)', 'KeXue(qfc17)', 'YuWen(qfc13)', 'ShuXue(qfc14)']]
        ]
        
        # 四年级课程
        grade4_classes = ['401', '402', '403', '404', '405']
        grade4_courses = [
            ['上午1', ['YuWen(qfc19)', 'ShuXue(qfc20)', 'YingYu(qfc21)', 'TiYu(qfc22)', 'KeXue(qfc23)']],
            ['上午2', ['ShuXue(qfc20)', 'YuWen(qfc19)', 'TiYu(qfc22)', 'KeXue(qfc23)', 'DeFa(qfc24)']],
            ['下午1', ['YingYu(qfc21)', 'KeXue(qfc23)', 'ShuXue(qfc20)', 'DeFa(qfc24)', 'YuWen(qfc19)']],
            ['下午2', ['TiYu(qfc22)', 'DeFa(qfc24)', 'KeXue(qfc23)', 'YuWen(qfc19)', 'ShuXue(qfc20)']]
        ]
        
        # 五年级课程
        grade5_classes = ['501', '502', '503', '504', '505']
        grade5_courses = [
            ['上午1', ['YuWen(qfc25)', 'ShuXue(qfc26)', 'YingYu(qfc27)', 'TiYu(qfc28)', 'KeXue(qfc29)']],
            ['上午2', ['ShuXue(qfc26)', 'YuWen(qfc25)', 'TiYu(qfc28)', 'KeXue(qfc29)', 'DeFa(qfc30)']],
            ['下午1', ['YingYu(qfc27)', 'KeXue(qfc29)', 'ShuXue(qfc26)', 'DeFa(qfc30)', 'YuWen(qfc25)']],
            ['下午2', ['TiYu(qfc28)', 'DeFa(qfc30)', 'KeXue(qfc29)', 'YuWen(qfc25)', 'ShuXue(qfc26)']]
        ]
        
        # 六年级课程
        grade6_classes = ['601', '602', '603', '604', '605']
        grade6_courses = [
            ['上午1', ['YuWen(qfc31)', 'ShuXue(qfc32)', 'YingYu(qfc33)', 'TiYu(qfc34)', 'KeXue(qfc35)']],
            ['上午2', ['ShuXue(qfc32)', 'YuWen(qfc31)', 'TiYu(qfc34)', 'KeXue(qfc35)', 'DeFa(qfc36)']],
            ['下午1', ['YingYu(qfc33)', 'KeXue(qfc35)', 'ShuXue(qfc32)', 'DeFa(qfc36)', 'YuWen(qfc31)']],
            ['下午2', ['TiYu(qfc34)', 'DeFa(qfc36)', 'KeXue(qfc35)', 'YuWen(qfc31)', 'ShuXue(qfc32)']]
        ]
        
        # 辅助函数：添加课程数据
        def add_courses(class_list, course_data):
            for i, class_id in enumerate(class_list):
                for time_slot, subjects in course_data:
                    if i < len(subjects):
                        subject_info = subjects[i]
                        # 解析课程名称和教师ID
                        subject_name = subject_info.split('(')[0]
                        teacher_id = subject_info.split('(')[1].replace(')', '')
                        
                        # 创建课程记录
                        course = Course(
                            class_name=class_id,
                            time_slot=time_slot,
                            subject=subject_name,
                            teacher_id=teacher_id
                        )
                        db.session.add(course)
        
        # 添加各年级课程
        add_courses(grade1_classes, grade1_courses)
        add_courses(grade2_classes, grade2_courses)
        add_courses(grade3_classes, grade3_courses)
        add_courses(grade4_classes, grade4_courses)
        add_courses(grade5_classes, grade5_courses)
        add_courses(grade6_classes, grade6_courses)
        
        # 提交课程数据
        db.session.commit()

