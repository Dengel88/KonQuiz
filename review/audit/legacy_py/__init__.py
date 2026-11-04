"""Банки вопросов. Каждый банк отдаёт CHOICE/EXACT в едином формате с фактом:

CHOICE: категория -> [(сложность 1..3, текст, правильный, [3 неправильных], факт)]
EXACT:  категория -> [(сложность 1..3, текст, число, это_год, факт)]

Правила для числовых: только устойчивые факты и неотрицательные целые (на клавиатуре клиента
нет минуса и запятой). Для «Крипты» и «ИИ» — только история и устройство, никаких курсов,
капитализаций и «самых новых моделей»: они устаревают за месяцы.
"""

from types import SimpleNamespace

from app.questions import ai, crypto, general
from app.questions.general_facts import FACTS


def _general() -> SimpleNamespace:
    return SimpleNamespace(
        CHOICE={c: [(*q, FACTS.get(q[1])) for q in items] for c, items in general.CHOICE.items()},
        EXACT={c: [(*q, FACTS.get(q[1])) for q in items] for c, items in general.EXACT.items()},
    )


BANKS = [_general(), crypto, ai]
