const classId = window.location.pathname.split('/')[2];
const timeSlotOrder = ['上午1','上午2','下午1','下午2'];
async function fetchClassCourses() {
    try {
        const courses = await api(`/api/class/${encodeURIComponent(classId)}/courses`);
        courses.sort((a,b) => timeSlotOrder.indexOf(a.time_slot) - timeSlotOrder.indexOf(b.time_slot));
        document.getElementById('scheduleBody').innerHTML = courses.length ? courses.map(course => `<tr>
            <td>${escapeHtml(t(course.time_slot))}</td><td>${escapeHtml(t(course.subject))}</td>
            <td>${escapeHtml(course.current_teacher)}</td><td>${escapeHtml(t(course.adjustment ? '已调课' : '正常'))}</td>
            </tr>`).join('') : `<tr><td colspan="4">${escapeHtml(t('暂无课程数据'))}</td></tr>`;
        document.getElementById('adjustmentNotices').innerHTML = courses.filter(c => c.adjustment).map(course => `
            <div class="adjustment-notice"><div class="notice-title">${escapeHtml(t(course.time_slot))} ${escapeHtml(t(course.subject))} ${escapeHtml(t('调课通知'))}</div>
            <div>${escapeHtml(t('原教师'))}: ${escapeHtml(course.original_teacher)} → ${escapeHtml(t('接课教师'))}: ${escapeHtml(course.current_teacher)}</div></div>`).join('');
        document.getElementById('lastUpdate').textContent = new Date().toLocaleString(locale);
    } catch (error) {
        document.getElementById('scheduleBody').innerHTML = `<tr><td colspan="4" class="error">${escapeHtml(error.message || t('加载失败，请重试'))}</td></tr>`;
    }
}
fetchClassCourses();
setInterval(fetchClassCourses, 30000);
