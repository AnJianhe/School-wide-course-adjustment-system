let currentCourseId = null;
const adjustModal = document.getElementById('adjustModal');
function openAdjustModal(courseId) {
    currentCourseId = courseId;
    document.getElementById('courseId').value = courseId;
    adjustModal.style.display = 'block';
}
function closeAdjustModal() {
    adjustModal.style.display = 'none';
    document.getElementById('adjustForm').reset();
}
window.addEventListener('click', e => { if (e.target === adjustModal) closeAdjustModal(); });
const tabs = document.querySelectorAll('.tab-btn');
tabs.forEach(button => button.addEventListener('click', () => {
    tabs.forEach(b => b.classList.toggle('active', b === button));
    document.getElementById('received-content').style.display = button.dataset.tab === 'received' ? 'block' : 'none';
    document.getElementById('sent-content').style.display = button.dataset.tab === 'sent' ? 'block' : 'none';
    loadRequests();
}));
document.getElementById('adjustForm').addEventListener('submit', async e => {
    e.preventDefault();
    const button = e.submitter;
    button.disabled = true;
    try {
        const result = await api('/api/adjustment/request', {
            course_id:currentCourseId, target_teacher_id:document.getElementById('targetTeacher').value,
            reason:document.getElementById('reason').value
        });
        alert(result.message);
        closeAdjustModal();
        await loadRequests();
    } catch (error) { alert(error.message || t('提交申请失败，请重试')); }
    finally { button.disabled = false; }
});
const statusText = {pending:'待处理', approved:'已批准', rejected:'已拒绝'};
function requestDescription(req) {
    return `${escapeHtml(req.class_name)} ${escapeHtml(t(req.time_slot))} ${escapeHtml(t(req.subject))}<br>${escapeHtml(req.reason)}`;
}
function tableRows(requests, received) {
    if (!requests.length) return `<p class="no-data">${escapeHtml(t(received ? '暂无收到的调课申请' : '暂无已发送的调课申请'))}</p>`;
    return `<table class="request-table"><thead><tr>
        <th>${escapeHtml(t('课程'))}</th><th>${escapeHtml(t(received ? '申请人' : '目标教师'))}</th>
        <th>${escapeHtml(t('状态'))}</th><th>${escapeHtml(t(received ? '操作' : '提交时间'))}</th>
        </tr></thead><tbody>${requests.map(req => `<tr>
        <td>${requestDescription(req)}</td><td>${escapeHtml(received ? req.from_teacher : req.to_teacher)}</td>
        <td class="status-${req.status}">${escapeHtml(t(statusText[req.status] || req.status))}</td>
        <td>${received ? (req.status === 'pending' ?
            `<button data-id="${req.id}" data-action="approve">${escapeHtml(t('批准'))}</button>
             <button data-id="${req.id}" data-action="reject">${escapeHtml(t('拒绝'))}</button>` : '-') :
            escapeHtml(new Date(req.created_at * 1000).toLocaleString(locale))}</td></tr>`).join('')}</tbody></table>`;
}
async function loadRequests() {
    try {
        const result = await api('/api/teacher/adjustments');
        document.getElementById('received-content').innerHTML = tableRows(result.received, true);
        document.getElementById('sent-content').innerHTML = tableRows(result.sent, false);
    } catch (error) {
        for (const id of ['received-content','sent-content']) {
            document.getElementById(id).textContent = error.message || t('加载失败，请重试');
        }
    }
}
document.getElementById('received-content').addEventListener('click', async e => {
    const button = e.target.closest('button[data-action]');
    if (!button) return;
    button.disabled = true;
    try {
        const result = await api(`/api/adjustment/${button.dataset.id}/handle`, {action:button.dataset.action});
        alert(result.message);
        window.location.reload();
    } catch (error) { alert(error.message || t('处理申请失败，请重试')); button.disabled = false; }
});
loadRequests();
