import json
from pathlib import Path
from flask import g, has_request_context, request

LANGUAGES = {
    'zh-CN': '简体中文', 'zh-TW': '繁體中文', 'en': 'English', 'ja': '日本語',
    'ko': '한국어', 'fr': 'Français', 'de': 'Deutsch', 'es': 'Español',
    'pt': 'Português', 'ru': 'Русский', 'ar': 'العربية', 'hi': 'हिन्दी',
    'it': 'Italiano', 'nl': 'Nederlands', 'tr': 'Türkçe', 'vi': 'Tiếng Việt',
    'th': 'ไทย', 'id': 'Bahasa Indonesia', 'ms': 'Bahasa Melayu', 'pl': 'Polski',
}
CATALOGS = {}
for language in LANGUAGES:
    path = Path(__file__).parent / 'locales' / (language + '.json')
    CATALOGS[language] = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def detect_language():
    selected = request.cookies.get('language')
    if selected in LANGUAGES:
        return selected
    # 按浏览器的偏好和权重匹配，包括地区代码与繁体别名。
    aliases = {'zh': 'zh-CN', 'zh-Hans': 'zh-CN', 'zh-Hant': 'zh-TW', 'zh-HK': 'zh-TW'}
    best = request.accept_languages.best_match(list(LANGUAGES) + list(aliases), default='zh-CN')
    return aliases.get(best, best)


def translate(message):
    locale = getattr(g, 'locale', 'zh-CN') if has_request_context() else 'zh-CN'
    return CATALOGS[locale].get(message, message)
