'use strict';
const translations = JSON.parse(document.getElementById('translations').textContent);
const locale = document.documentElement.lang;
function t(message) { return translations[message] ?? message; }
function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
}
async function api(url, data) {
    const options = data === undefined ? {} : {
        method: 'POST', headers: {'Content-Type':'application/json',
            'X-CSRF-Token':document.querySelector('meta[name=csrf-token]').content},
        body:JSON.stringify(data)
    };
    const response = await fetch(url, options);
    if (response.status === 401) { window.location.assign('/'); throw new Error(t('请先登录')); }
    const result = await response.json();
    if (!response.ok || result.status === 'error') throw new Error(result.message || t('加载失败，请重试'));
    return result;
}
