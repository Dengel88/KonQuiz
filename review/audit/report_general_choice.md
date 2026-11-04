# Аудит: general_choice (200 вопросов CHOICE, «Общая»)

## Сводка

- **OK:** 188 · **FIX:** 11 · **DROP:** 0 · **RISK:** 1
- **Средняя интересность:** 2,6 из 5
- **Сложность в банке:** 1 — 127, 2 — 66, 3 — 7. Предложенная по итогам проверки: 1 — 123, 2 — 72, 3 — 5. Почти все вопросы с «3» (042, 068, 073, 117) на деле тянут на 2.

### Главные системные проблемы
1. **Ошибки в «интересных фактах» встречаются чаще, чем в ответах.** Сами ответы почти везде верны, а вот факты местами врут: Россия «больше Южной Америки» (052), Кутузову «67 лет» (005), Аляска «вдвое больше Техаса» (072), Бегемот «заплатив за проезд» (159), День России «в честь выборов Ельцина» (020). Когда факт показывают как «ого», ошибку в нём легко заметить и переслать.
2. **Дубли по сюжету.** Колизей (008/061), пирамида Хеопса (015/040), Мачу-Пикчу (041/054), Теночтитлан/Мехико (042/082 — факты почти одинаковые), «Титаник» (175/180), Колумб (004/033), Петербург (001/057/089). В одном матче игрок может получить два вопроса с одним ответом. Нужен тег-кластер, чтобы не выдавать их в одной игре.
3. **Банк перекошен в сторону зубрёжки «Столица X?» и «Кто написал X?».** Только столиц — 16, ещё около 20 вопросов в формате «автор → произведение». Догадаться рассуждением в них нельзя, отсюда низкая средняя интересность.
4. **Очень мало вопросов сложности 3** (по сути 5 из 200). Знатокам нечем отличиться.
5. **Частичная правота в неверных вариантах.** Багратион и Барклай-де-Толли при Бородине действительно командовали армиями (005); «лёгкие» по площади поверхности больше кожи (121).
6. **Слабые или несуществующие дистракторы.** «Go» — не химический элемент (097); перестановки «World Web Wide» (196) угадываются за секунду.
7. **Устаревание реалий:** с 2022 года на новой сторублёвке Большого театра нет (174).

### Чего не хватает
- **Россия и её регионы** (игра идёт на карте России!): реки, города, достопримечательности регионов, «какой город — столица какого края».
- **Быт и современность:** еда и кухни мира, бренды и происхождение вещей, языки и слова, мифология, музыка XX–XXI века (поп и рок), мультфильмы и сериалы последних 20 лет.
- **Спорт и техника:** 7 и 5 вопросов, все сложности 1–2.
- **Вопросы на рассуждение уровня 2–3** («почему…», «что из этого появилось раньше…»).

## Проблемные вопросы

| id | вердикт | что не так | как исправить (готовый текст) | источник |
|---|---|---|---|---|
| general_choice-005 | FIX | При Бородине Багратион командовал 2-й Западной армией, а Барклай-де-Толли — 1-й, так что эти варианты формально тоже верны. Год рождения Кутузова спорен (1745 или 1747), поэтому «67 лет» не подтверждается. | Вопрос: «Кто был главнокомандующим русскими войсками в Бородинском сражении?» Неверные: «Александр Суворов / Пётр Румянцев / Григорий Потёмкин». Факт: «Кутузов принял армию за две недели до Бородина; после сражения он решился оставить Москву, чтобы сохранить войско». | [БРЭ](https://bigenc.ru/c/kutuzov-mikhail-illarionovich-081731) |
| general_choice-020 | FIX | Факт неточен: День России отмечают в честь Декларации о суверенитете РСФСР (12.06.1990), а не выборов президента. Путин и Медведев в вариантах — действующая политика, такие варианты лучше не ставить. | Неверные: «Михаил Горбачёв / Александр Руцкой / Виктор Черномырдин». Факт: «Ельцина избрали 12 июня 1991 года — ровно через год после принятия Декларации о суверенитете РСФСР; именно её годовщину отмечают как День России». | общеизвестно (ФЗ о праздниках, Декларация 12.06.1990) |
| general_choice-025 | RISK | Тема присоединения Крыма — спорная территория и сегодня политически острая, хотя сам вопрос исторический (1783). | Решение за редакцией. Безопасная замена той же сложности: «При какой императрице открыли Эрмитаж?» Ответ: Екатерине II; неверные: «Елизавете Петровне / Анне Иоанновне / Екатерине I». Факт: «Эрмитаж ведёт отсчёт с 1764 года, когда Екатерина II купила коллекцию из 225 картин». | общеизвестно |
| general_choice-052 | FIX | Факт неверен: площадь Южной Америки около 17,8 млн км², больше России (17,1). | Факт: «Площадь России — около 17,1 млн км²; это больше площади поверхности Плутона (около 16,7 млн км²)». | Britannica (South America ≈17,8 млн км²), NASA (Pluto) |
| general_choice-072 | FIX | Аляска больше Техаса в 2,5 раза (1,72 млн км² против 0,70 млн км²), а не «вдвое». | Факт: «Аляска почти в два с половиной раза больше Техаса; США купили её у России в 1867 году за 7,2 млн долларов». | US Census Bureau, площади штатов |
| general_choice-087 | FIX | Число мостов в Берлине разнится от источника к источнику — от ~960 до ~2100 в зависимости от методики, так что «около 1700» не подтверждается. | Факт: «Мостов в Берлине (по разным подсчётам — от тысячи до двух) в несколько раз больше, чем в Венеции, где их около 400». | [berlin.de](https://www.berlin.de/sen/uvk/mobilitaet-und-verkehr/infrastruktur/brueckenbau/masterplan-bruecken/), [The Local](https://www.thelocal.de/20180816/report) |
| general_choice-097 | FIX | Вариант «Go» — несуществующий символ, его отбрасывают сразу. | Неверные: «Ag / Ar / Al». | — |
| general_choice-121 | FIX | Внутренняя поверхность лёгких (альвеолы) — десятки м², больше кожи, так что вариант «Лёгкие» формально верен. | Вопрос: «Какой орган человека самый большой и тяжёлый?» Неверные: «Печень / Мозг / Сердце». Факт: «Кожа взрослого весит несколько килограммов и занимает около 2 м² — это больше, чем у печени, самого крупного внутреннего органа». | общеизвестно |
| general_choice-159 | FIX | Ошибка в факте: в романе кондукторша не пустила кота, и Бегемот уехал «зайцем», уцепившись за трамвай снаружи. | Факт: «Кот Бегемот пытался честно заплатить за трамвай гривенником, а когда кондукторша его выгнала, уехал, прицепившись к трамваю сзади». | Булгаков, «Мастер и Маргарита», гл. 4 |
| general_choice-168 | FIX | Скобка «(медведей дописал Савицкий)» в вопросе лишняя: она удлиняет чтение больше 4 секунд и дублирует факт. | Вопрос: «Кто написал картину «Утро в сосновом лесу»?» Факт без изменений. | — |
| general_choice-174 | FIX | Устарело: на сторублёвке образца 2022 года — Спасская башня и Ржевский мемориал. Старые купюры ещё ходят, ответ становится спорным. | Вопрос: «Квадрига какого бога венчает Большой театр?» Ответ: «Аполлона». Неверные: «Зевса / Гелиоса / Посейдона». Факт: «Бронзовую квадригу Аполлона на Большом театре отлил Пётр Клодт; её изображение было на сторублёвке до 2022 года». Сложность 2. | [ЦБ РФ](https://cbr.ru/cash_circulation/mb), [Inc.](https://incrussia.ru/news/tsb-vypustil-v-obrashhenie-obnovlennuyu-storublevku-na-nej-kreml-rzhev-i-qr-kod/) |
| general_choice-196 | FIX | Неверные варианты — перестановки слов, правильный угадывается мгновенно, вопрос ничего не проверяет. | Вопрос: «Кто придумал Всемирную паутину (WWW)?» Ответ: «Тим Бернерс-Ли». Неверные: «Билл Гейтс / Стив Джобс / Винтон Серф». Факт: «Тим Бернерс-Ли придумал WWW в ЦЕРН в 1989 году и не стал её патентовать; первый сайт info.cern.ch открывается до сих пор». Сложность 2. | общеизвестно |

Мелкие замечания (без вердикта, на усмотрение редакции):
- **044:** 21 июля — дата по UTC и Москве, в США было 20-е. Можно уточнить в факте.
- **117:** 0(I) Rh− — универсальный донор только эритроцитов. Для викторины допустимо.
- **035, 012:** трагедии упоминаются фактологично, без развлекательной подачи — оставлены OK.

## interest (id | интерес 1–5 | предложенная сложность 1–3)

general_choice-001 | 2 | 1
general_choice-002 | 2 | 1
general_choice-003 | 2 | 1
general_choice-004 | 3 | 1
general_choice-005 | 2 | 2
general_choice-006 | 3 | 2
general_choice-007 | 3 | 2
general_choice-008 | 3 | 1
general_choice-009 | 2 | 2
general_choice-010 | 3 | 2
general_choice-011 | 3 | 2
general_choice-012 | 2 | 1
general_choice-013 | 2 | 2
general_choice-014 | 2 | 1
general_choice-015 | 4 | 2
general_choice-016 | 3 | 1
general_choice-017 | 3 | 2
general_choice-018 | 3 | 2
general_choice-019 | 3 | 2
general_choice-020 | 2 | 1
general_choice-021 | 2 | 1
general_choice-022 | 2 | 1
general_choice-023 | 2 | 2
general_choice-024 | 2 | 1
general_choice-025 | 2 | 2
general_choice-026 | 3 | 2
general_choice-027 | 4 | 2
general_choice-028 | 4 | 2
general_choice-029 | 3 | 1
general_choice-030 | 3 | 2
general_choice-031 | 2 | 1
general_choice-032 | 3 | 2
general_choice-033 | 3 | 2
general_choice-034 | 2 | 1
general_choice-035 | 2 | 1
general_choice-036 | 2 | 1
general_choice-037 | 3 | 1
general_choice-038 | 3 | 1
general_choice-039 | 3 | 2
general_choice-040 | 3 | 1
general_choice-041 | 3 | 2
general_choice-042 | 3 | 2
general_choice-043 | 2 | 1
general_choice-044 | 2 | 1
general_choice-045 | 3 | 2
general_choice-046 | 2 | 2
general_choice-047 | 4 | 2
general_choice-048 | 3 | 1
general_choice-049 | 3 | 2
general_choice-050 | 2 | 1
general_choice-051 | 2 | 1
general_choice-052 | 2 | 1
general_choice-053 | 4 | 2
general_choice-054 | 2 | 2
general_choice-055 | 4 | 1
general_choice-056 | 2 | 1
general_choice-057 | 2 | 1
general_choice-058 | 3 | 1
general_choice-059 | 4 | 2
general_choice-060 | 2 | 1
general_choice-061 | 2 | 1
general_choice-062 | 3 | 2
general_choice-063 | 2 | 1
general_choice-064 | 2 | 1
general_choice-065 | 2 | 1
general_choice-066 | 3 | 2
general_choice-067 | 2 | 1
general_choice-068 | 3 | 2
general_choice-069 | 3 | 1
general_choice-070 | 3 | 2
general_choice-071 | 2 | 1
general_choice-072 | 3 | 2
general_choice-073 | 3 | 2
general_choice-074 | 4 | 2
general_choice-075 | 2 | 1
general_choice-076 | 2 | 1
general_choice-077 | 3 | 2
general_choice-078 | 2 | 1
general_choice-079 | 2 | 1
general_choice-080 | 3 | 2
general_choice-081 | 2 | 1
general_choice-082 | 2 | 1
general_choice-083 | 3 | 2
general_choice-084 | 4 | 2
general_choice-085 | 3 | 2
general_choice-086 | 3 | 1
general_choice-087 | 2 | 1
general_choice-088 | 3 | 2
general_choice-089 | 2 | 1
general_choice-090 | 3 | 2
general_choice-091 | 3 | 1
general_choice-092 | 4 | 3
general_choice-093 | 3 | 2
general_choice-094 | 3 | 3
general_choice-095 | 4 | 3
general_choice-096 | 3 | 1
general_choice-097 | 3 | 1
general_choice-098 | 2 | 1
general_choice-099 | 2 | 1
general_choice-100 | 3 | 1
general_choice-101 | 3 | 1
general_choice-102 | 2 | 1
general_choice-103 | 3 | 2
general_choice-104 | 2 | 1
general_choice-105 | 3 | 1
general_choice-106 | 3 | 2
general_choice-107 | 2 | 1
general_choice-108 | 2 | 1
general_choice-109 | 4 | 2
general_choice-110 | 2 | 1
general_choice-111 | 3 | 2
general_choice-112 | 2 | 1
general_choice-113 | 2 | 1
general_choice-114 | 2 | 1
general_choice-115 | 2 | 1
general_choice-116 | 3 | 2
general_choice-117 | 3 | 3
general_choice-118 | 1 | 1
general_choice-119 | 2 | 2
general_choice-120 | 4 | 3
general_choice-121 | 4 | 2
general_choice-122 | 4 | 2
general_choice-123 | 1 | 1
general_choice-124 | 2 | 1
general_choice-125 | 3 | 2
general_choice-126 | 2 | 2
general_choice-127 | 2 | 1
general_choice-128 | 2 | 1
general_choice-129 | 3 | 1
general_choice-130 | 2 | 1
general_choice-131 | 3 | 1
general_choice-132 | 3 | 1
general_choice-133 | 3 | 1
general_choice-134 | 2 | 1
general_choice-135 | 3 | 1
general_choice-136 | 3 | 1
general_choice-137 | 3 | 2
general_choice-138 | 2 | 1
general_choice-139 | 3 | 1
general_choice-140 | 2 | 1
general_choice-141 | 3 | 1
general_choice-142 | 3 | 1
general_choice-143 | 1 | 1
general_choice-144 | 2 | 1
general_choice-145 | 2 | 1
general_choice-146 | 2 | 1
general_choice-147 | 3 | 1
general_choice-148 | 2 | 1
general_choice-149 | 2 | 1
general_choice-150 | 2 | 1
general_choice-151 | 2 | 2
general_choice-152 | 2 | 1
general_choice-153 | 2 | 1
general_choice-154 | 2 | 1
general_choice-155 | 2 | 1
general_choice-156 | 3 | 1
general_choice-157 | 2 | 1
general_choice-158 | 2 | 2
general_choice-159 | 4 | 2
general_choice-160 | 2 | 1
general_choice-161 | 2 | 1
general_choice-162 | 3 | 1
general_choice-163 | 2 | 1
general_choice-164 | 2 | 1
general_choice-165 | 3 | 1
general_choice-166 | 2 | 1
general_choice-167 | 3 | 2
general_choice-168 | 4 | 2
general_choice-169 | 2 | 2
general_choice-170 | 2 | 2
general_choice-171 | 3 | 1
general_choice-172 | 2 | 1
general_choice-173 | 3 | 2
general_choice-174 | 4 | 2
general_choice-175 | 2 | 1
general_choice-176 | 4 | 2
general_choice-177 | 4 | 1
general_choice-178 | 3 | 1
general_choice-179 | 2 | 1
general_choice-180 | 2 | 1
general_choice-181 | 2 | 1
general_choice-182 | 2 | 1
general_choice-183 | 2 | 1
general_choice-184 | 3 | 2
general_choice-185 | 2 | 1
general_choice-186 | 3 | 1
general_choice-187 | 1 | 1
general_choice-188 | 2 | 1
general_choice-189 | 2 | 1
general_choice-190 | 3 | 2
general_choice-191 | 3 | 2
general_choice-192 | 3 | 2
general_choice-193 | 2 | 1
general_choice-194 | 4 | 2
general_choice-195 | 2 | 1
general_choice-196 | 3 | 1
general_choice-197 | 2 | 2
general_choice-198 | 2 | 1
general_choice-199 | 3 | 1
general_choice-200 | 4 | 2
