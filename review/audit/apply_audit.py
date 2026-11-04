"""Применение аудита 2026-10-01 к app/questions/data/*.json (одноразовый скрипт, хранится для истории).

python review/audit/apply_audit.py
Правки — по report_*.md. Совсем другой вопрос вместо старого получает НОВЫЙ ключ (старый уходит
из файлов и в базе выключается), чтобы оценки игроков не переехали на чужой вопрос.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "app" / "questions" / "data"
AUDIT = ROOT / "review" / "audit"

# ------------------------------------------------------------------ правки (FIX)
FIX = {
    # --- general_choice
    "general_choice-005": dict(
        text="Кто был главнокомандующим русскими войсками в Бородинском сражении?",
        wrong=["Александр Суворов", "Пётр Румянцев", "Григорий Потёмкин"],
        fact="Кутузов принял армию за две недели до Бородина; после сражения он решился оставить Москву, чтобы сохранить войско."),
    "general_choice-020": dict(
        wrong=["Михаил Горбачёв", "Александр Руцкой", "Виктор Черномырдин"],
        fact="Ельцина избрали 12 июня 1991 года — ровно через год после принятия Декларации о суверенитете РСФСР; именно её годовщину отмечают как День России."),
    "general_choice-052": dict(
        fact="Площадь России — около 17,1 млн км²; это больше площади поверхности Плутона (около 16,7 млн км²)."),
    "general_choice-072": dict(
        fact="Аляска почти в два с половиной раза больше Техаса; США купили её у России в 1867 году за 7,2 млн долларов."),
    "general_choice-087": dict(
        fact="Мостов в Берлине (по разным подсчётам — от тысячи до двух) в несколько раз больше, чем в Венеции, где их около 400."),
    "general_choice-097": dict(wrong=["Ag", "Ar", "Al"]),
    "general_choice-121": dict(
        text="Какой орган человека самый большой и тяжёлый?",
        wrong=["Печень", "Мозг", "Сердце"],
        fact="Кожа взрослого весит несколько килограммов и занимает около 2 м² — это больше, чем у печени, самого крупного внутреннего органа."),
    "general_choice-159": dict(
        fact="Кот Бегемот пытался честно заплатить за трамвай гривенником, а когда кондукторша его выгнала, уехал, прицепившись к трамваю сзади."),
    "general_choice-168": dict(text="Кто написал картину «Утро в сосновом лесу»?"),
    "general_choice-196": dict(
        text="Кто придумал Всемирную паутину (WWW)?", correct="Тим Бернерс-Ли",
        wrong=["Билл Гейтс", "Стив Джобс", "Винтон Серф"], difficulty=2,
        fact="Тим Бернерс-Ли придумал WWW в ЦЕРН в 1989 году и не стал её патентовать; первый сайт info.cern.ch открывается до сих пор."),
    # --- general_exact
    "general_exact-024": dict(
        fact="Компьенское перемирие подписали в железнодорожном вагоне около пяти утра 11 ноября 1918 года, а огонь прекратили в 11:00 — «в 11-й час 11-го дня 11-го месяца»."),
    "general_exact-031": dict(
        fact="Авария произошла 26 апреля 1986 года; на следующий день почти 50 тысяч жителей Припяти вывезли примерно за три часа — люди думали, что уезжают на пару дней."),
    "general_exact-037": dict(
        text="Сколько минут длился полёт Гагарина по официальным данным?",
        fact="Официально — 108 минут, но по рассекреченным документам — около 106. Гагарин приземлился на парашюте отдельно от спускаемого аппарата."),
    "general_exact-073": dict(
        text="Максимальная глубина Байкала в метрах (по современным данным)?",
        fact="Байкал — глубочайшее озеро мира: 1642 м (в некоторых источниках — 1637 м); прозрачность воды доходит до 40 метров."),
    "general_exact-077": dict(
        fact="Останкинская башня высотой 540 м в 1967 году стала самым высоким свободностоящим сооружением мира и держала рекорд девять лет — до башни Си-Эн в Торонто."),
    "general_exact-078": dict(
        fact="Эльбрус высотой 5642 м — высшая точка России, а по самой распространённой версии границы — и Европы. Это потухший вулкан с двумя вершинами."),
    "general_exact-080": dict(text="Высота Килиманджаро в метрах (официальная, по данным Танзании)?"),
    "general_exact-081": dict(
        fact="Бурдж-Халифа высотой 828 м в 2010 году стала самым высоким зданием мира; строили её шесть лет."),
    "general_exact-094": dict(
        text="Сколько тысяч озёр площадью больше 500 м² в Финляндии (примерно)?", correct=188,
        fact="Финляндию зовут «страной тысячи озёр», а на деле их почти 188 тысяч, если считать водоёмы от 500 м². Крупнее 10 гектаров — всего около 5600."),
    "general_exact-097": dict(
        fact="В 2015 году Денали перемерили по GPS: 6190 м вместо прежних 6194. Гора не уменьшилась — просто измерили точнее."),
    "general_exact-103": dict(
        text="Длина железной дороги Москва — Санкт-Петербург в километрах?", correct=645,
        fact="Николаевскую дорогу длиной 645 км открыли в 1851 году; она почти идеально прямая, а «Сапсан» проходит её примерно за 4 часа."),
    "general_exact-133": dict(
        fact="Nintendo основана в 1889 году в Киото как фабрика игральных карт ханафуда — и выпускает их до сих пор."),
    "general_exact-145": dict(
        text="Сколько раз Бразилия выигрывала чемпионат мира по футболу в XX веке?", correct=4,
        fact="Бразилия побеждала в 1958, 1962, 1970 и 1994 годах, пятый титул взяла в 2002-м; это единственная сборная, игравшая на всех чемпионатах мира."),
    "general_exact-158": dict(
        fact="В сутках 86 400 секунд. Иногда к суткам добавляли «високосную секунду», но к 2035 году от неё решили отказаться."),
    # --- ai
    "ai-016": dict(fact="AlexNet обучали на двух игровых видеокартах; по доле ошибок (15,3% против 26,2%) она обошла ближайшего соперника почти на 11 пунктов."),
    "ai-018": dict(text="Кто из них получил Нобелевскую премию по физике 2024 года за основы машинного обучения?"),
    "ai-019": dict(fact="Половину премии Хассабис разделил с Джоном Джампером за AlphaFold, вторую половину получил Дэвид Бейкер за компьютерный дизайн белков."),
    "ai-021": dict(text="Как называлась нейросеть OpenAI 2021 года, рисующая картинки по тексту?", correct="DALL·E",
                   wrong=["Midjourney", "Stable Diffusion", "Imagen"]),
    "ai-028": dict(replace_wrong={"Слишком долгое обучение на GPU": "Обучение на устаревших видеокартах"}),
    "ai-031": dict(fact="В 1958 году New York Times писала, что ВМС США ждут от перцептрона умения ходить, говорить и осознавать себя."),
    "ai-035": dict(text="Как звали первого ИИ-помощника Тони Старка в фильмах Marvel?", correct="Джарвис",
                   wrong=["Альтрон", "Вижн", "Скайнет"]),
    "ai-060": dict(text="Кто из них — сооснователь DeepMind?"),
    "ai-061": dict(text="Кто из бывших руководителей исследований OpenAI основал Anthropic?",
                   fact="Anthropic Дарио Амодеи основал вместе с сестрой Даниэлой и группой коллег из OpenAI."),
    "ai-062": dict(text="Кто из них — сооснователь NVIDIA?"),
    "ai-065": dict(replace_wrong={"Uber Eats": "Aurora"}),
    "ai-074": dict(replace_wrong={"Скамейка в дата-центре": "Тип нейросети"}),
    "ai-077": dict(replace_wrong={"Определять погоду": "Распознавать лица на фото"}),
    "ai-087": dict(text="В каком году Вейценбаум опубликовал статью о программе ELIZA?", correct=1966),
    "ai-099": dict(fact="Цену Google не раскрыла; по данным прессы — от 400 до 650 млн долларов, сделку лично вёл Ларри Пейдж."),
    "ai-102": dict(text="В каком году вышла первая публичная версия CUDA?", correct=2007,
                   fact="CUDA анонсировали в ноябре 2006 года с GeForce 8800 GTX, а SDK для разработчиков вышел в феврале 2007-го."),
    # --- crypto
    "crypto-007": dict(replace_wrong={"Эирдроп": "Эйрдроп"}),
    "crypto-015": dict(text="Из скольких слов чаще всего состоит сид-фраза?",
                       fact="Стандарт BIP-39 допускает 12, 15, 18, 21 или 24 слова из списка в 2048; на практике почти всегда 12 или 24."),
    "crypto-053": dict(text="Что такое эйрдроп (airdrop)?"),
    "crypto-058": dict(text="Какой стейблкоин изначально выпустил протокол MakerDAO?", difficulty=3,
                       fact="DAI появился в 2017 году как стейблкоин под криптовалютный залог; в 2024-м MakerDAO переименовали в Sky."),
    "crypto-069": dict(wrong=["Децентрализованная (DEX)", "Некастодиальная", "Одноранговая (P2P)"]),
    "crypto-076": dict(wrong=["Акции Telegram", "Стикерпаки", "Облачное хранилище"],
                       fact="Fragment проводит аукционы коротких юзернеймов и номеров +888 за TON; там же покупают Stars и Premium."),
    "crypto-090": dict(fact="Награда за блок начиналась с 50 BTC и каждые ~4 года уменьшается вдвое; в 2024 году она снизилась до 3,125 BTC."),
    "crypto-097": dict(fact="Mt. Gox объявила о банкротстве в феврале 2014 года, а первые выплаты кредиторам начались лишь летом 2024-го — через десять лет."),
    "crypto-107": dict(fact="Coinbase основана в 2012 году в Сан-Франциско; в апреле 2021-го её акции начали торговаться на Nasdaq под тикером COIN."),
    "crypto-118": dict(text="Сколько секунд длился слот блока в Ethereum сразу после перехода на PoS в 2022 году?",
                       fact="С 2022 года каждые 12 секунд случайно выбранный валидатор предлагает блок; разработчики обсуждают сокращение слота вдвое."),
}

# ------------------------------------------------------------------ убрать (DROP) и заменить новым вопросом
DROP = {"general_exact-090", "general_exact-117", "ai-096", "ai-111", "crypto-025",
        # заменяются ниже вопросами с новыми ключами
        "general_choice-025", "general_choice-174", "ai-059", "crypto-083"}

NEW = {
    "general": [
        dict(key="general_choice-201", type="CHOICE", category="История", difficulty=2,
             text="При какой императрице открыли Эрмитаж?", correct="Екатерине II",
             wrong=["Елизавете Петровне", "Анне Иоанновне", "Екатерине I"],
             fact="Эрмитаж ведёт отсчёт с 1764 года, когда Екатерина II купила коллекцию из 225 картин."),
        dict(key="general_choice-202", type="CHOICE", category="Искусство", difficulty=2,
             text="Квадрига какого бога венчает Большой театр?", correct="Аполлона",
             wrong=["Зевса", "Гелиоса", "Посейдона"],
             fact="Бронзовую квадригу Аполлона на Большом театре отлил Пётр Клодт; её изображение было на сторублёвке до 2022 года."),
        dict(key="general_exact-160", type="EXACT", category="Культура", difficulty=2,
             text="Сколько лет было Лермонтову, когда он погиб?", correct=26, is_year=False,
             fact="Лермонтов погиб на дуэли у подножия Машука в 1841 году; на смерть Пушкина четырьмя годами раньше он откликнулся стихотворением «Смерть поэта»."),
    ],
    "ai": [
        dict(key="ai-119", type="CHOICE", category="ИИ", difficulty=2,
             text="Кого совет директоров OpenAI в ноябре 2023 года уволил с поста CEO, а через несколько дней вернул?",
             correct="Сэм Альтман", wrong=["Илон Маск", "Илья Суцкевер", "Сатья Наделла"],
             fact="После увольнения Альтмана более 700 из ~770 сотрудников OpenAI пригрозили уйти — и он вернулся через пять дней."),
    ],
    "crypto": [
        dict(key="crypto-126", type="CHOICE", category="Крипта", difficulty=2,
             text="Кто из братьев Дуровых писал техническую часть блокчейна TON?", correct="Николай Дуров",
             wrong=["Павел Дуров", "Виталик Бутерин", "Анатолий Яковенко"],
             fact="Николай Дуров — математик, многократный призёр олимпиад по программированию, автор протокола MTProto и white paper TON."),
    ],
}

# ------------------------------------------------------------------ группы: вопросы одного сюжета
GROUPS = {
    "colosseum": ["general_choice-008", "general_choice-061"],
    "cheops": ["general_choice-015", "general_choice-040"],
    "machu_picchu": ["general_choice-041", "general_choice-054"],
    "tenochtitlan": ["general_choice-042", "general_choice-082"],
    "titanic": ["general_choice-175", "general_choice-180"],
    "columbus": ["general_choice-004", "general_choice-033"],
    "petersburg": ["general_choice-001", "general_choice-057", "general_choice-089"],
    "pushkin_age": ["general_exact-104", "general_exact-107"],
    # крипта (report_crypto: кластеры)
    "pizza": ["crypto-024", "crypto-091", "crypto-092"],
    "halving": ["crypto-007", "crypto-088", "crypto-090", "crypto-103", "crypto-104"],
    "the_merge": ["crypto-006", "crypto-065", "crypto-094"],
    "ton_gram": ["crypto-010", "crypto-011", "crypto-012", "crypto-105", "crypto-126"],
    "seed_phrase": ["crypto-014", "crypto-015", "crypto-051", "crypto-109"],
    "hashcash": ["crypto-047", "crypto-116"],
    "bmoney_wei": ["crypto-004", "crypto-046", "crypto-095"],
    "mtgox": ["crypto-040", "crypto-097", "crypto-098"],
    "bitcoin_cash": ["crypto-035", "crypto-114"],
    "cryptopunks": ["crypto-082", "crypto-121", "crypto-122"],
    "crypto_041_124": ["crypto-041", "crypto-124"],
    "crypto_042_125": ["crypto-042", "crypto-125"],
    "usdt": ["crypto-018", "crypto-112"],
    "dogecoin": ["crypto-009", "crypto-099"],
    "the_dao": ["crypto-036", "crypto-102"],
}
# ИИ: пары «вариант → числовой», где текст или факт одного выдаёт ответ другого (report_ai)
AI_PAIRS = """001-078 002-079 004-087 005-080 006-090 007-082 016-088 017-113 018-094 019-094 073-112
005-081 009-084 009-085 013-086 015-089 032-095 036-091 008-098 008-099 010-100 059-097 062-101
048-102 031-118 037-105 038-104 075-115 110-111"""


def ai_groups(keys: set[str]) -> dict[str, list[str]]:
    parent: dict[str, str] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            x = parent[x]
        return x

    for pair in AI_PAIRS.split():
        a, b = (f"ai-{n}" for n in pair.split("-"))
        if a in keys and b in keys:
            parent[find(a)] = find(b)
    clusters: dict[str, list[str]] = {}
    for k in parent:
        clusters.setdefault(find(k), []).append(k)
    return {f"ai_{min(v)[3:]}": sorted(v) for v in clusters.values() if len(v) > 1}


def interest_table() -> dict[str, tuple[int, int]]:
    """id | интерес | предложенная сложность — из хвоста каждого отчёта."""
    out = {}
    pat = re.compile(r"^\W*((?:general_choice|general_exact|crypto|ai)-\d{3})\W*\|\s*(\d)\s*\|\s*(\d)")
    for rep in AUDIT.glob("report_*.md"):
        for line in rep.read_text(encoding="utf-8").splitlines():
            m = pat.match(line)
            if m:
                out[m[1]] = (int(m[2]), int(m[3]))
    return out


def main() -> None:
    interest = interest_table()
    stats = dict(fixed=0, dropped=0, added=0, diff_changed=0, grouped=0, interest=0)
    for bank in ("general", "crypto", "ai"):
        path = DATA / f"{bank}.json"
        qs = json.loads(path.read_text(encoding="utf-8"))
        before = len(qs)
        qs = [q for q in qs if q["key"] not in DROP]
        stats["dropped"] += before - len(qs)
        for q in NEW.get(bank, []):
            qs.append({**q, "group": None})
            stats["added"] += 1
        by_key = {q["key"]: q for q in qs}

        for key, patch in FIX.items():
            if key not in by_key:
                continue
            q = by_key[key]
            patch = dict(patch)
            for old, new in patch.pop("replace_wrong", {}).items():
                assert old in q["wrong"], (key, old, q["wrong"])
                q["wrong"] = [new if w == old else w for w in q["wrong"]]
            q.update(patch)
            stats["fixed"] += 1

        for key, q in by_key.items():
            if key in interest:
                score, diff = interest[key]
                q["interest"] = score
                stats["interest"] += 1
                # явная сложность из FIX важнее оценки из хвоста отчёта
                if diff != q["difficulty"] and "difficulty" not in FIX.get(key, {}):
                    q["difficulty"] = diff
                    stats["diff_changed"] += 1

        groups = dict(GROUPS)
        if bank == "ai":
            groups.update(ai_groups(set(by_key)))
        for name, members in groups.items():
            present = [m for m in members if m in by_key]
            if len(present) < 2:
                continue
            for m in present:
                by_key[m]["group"] = name
                stats["grouped"] += 1

        # порядок полей: group и interest — в конце
        ordered = []
        for q in qs:
            rest = {k: v for k, v in q.items() if k not in ("group", "interest")}
            ordered.append({**rest, "group": q.get("group"), **({"interest": q["interest"]} if "interest" in q else {})})
        path.write_text("[\n" + ",\n".join(json.dumps(q, ensure_ascii=False) for q in ordered) + "\n]\n",
                        encoding="utf-8")
    print(stats)


if __name__ == "__main__":
    main()
