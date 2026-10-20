# Data-quality and naming report

Dataset: `C:\hack\astana-walks\data\pois.json`

* Schema version: 1; latest collection: 2026-10-20T06:40:10+00:00
* Places after validation and merging: **502**; skipped on load: none; merged on load: 0 
* Linked to Wikipedia/Wikidata (a link, not a popularity rating): 21
* Opening hours: 138 with OSM text, 131 parseable, 364 missing (shown as unknown)
* Wheelchair tag (source-reported): {'not tagged': 468, 'yes': 24, 'limited': 5, 'no': 5}
* Media: 14 with a photo, 21 with a description; Wikidata identity checks: not run yet
* collected_at is when the data was DOWNLOADED from OpenStreetMap. It does not mean opening hours or other details were verified on that date.

## Coverage (collected areas)

* None: centre {'lat': 51.089, 'lon': 71.416}, radius 2500 m, collected 2026-10-19T15:51:19+00:00, raw 112, kept 72
* None: centre {'lat': 51.129, 'lon': 71.42}, radius 2500 m, collected 2026-10-19T16:00:12+00:00, raw 359, kept 150
* area: centre {'lat': 51.089, 'lon': 71.416}, radius 2500 m, collected 2026-10-19T17:46:58+00:00, raw 114, kept 72
* area: centre {'lat': 51.129, 'lon': 71.42}, radius 2500 m, collected 2026-10-19T17:48:19+00:00, raw 363, kept 150
* area: centre {'lat': 51.165, 'lon': 71.43}, radius 2500 m, collected 2026-10-19T17:49:37+00:00, raw 380, kept 150
* landmarks: centre {'lat': 51.089, 'lon': 71.416}, radius citywide m, collected 2026-10-19T17:50:21+00:00, raw 44, kept 44
* area: centre {'lat': 51.089, 'lon': 71.416}, radius 2500 m, collected 2026-10-19T18:06:56+00:00, raw 114, kept 72
* area: centre {'lat': 51.129, 'lon': 71.42}, radius 2500 m, collected 2026-10-19T18:08:17+00:00, raw 363, kept 150
* area: centre {'lat': 51.165, 'lon': 71.43}, radius 2500 m, collected 2026-10-19T18:09:32+00:00, raw 380, kept 150
* landmarks: centre {'lat': 51.089, 'lon': 71.416}, radius citywide m, collected 2026-10-19T18:10:17+00:00, raw 44, kept 44
* area: centre {'lat': 51.089, 'lon': 71.416}, radius 2500 m, collected 2026-10-20T06:06:48+00:00, raw 114, kept 72
* area: centre {'lat': 51.129, 'lon': 71.42}, radius 2500 m, collected 2026-10-20T06:07:50+00:00, raw 363, kept 150
* area: centre {'lat': 51.165, 'lon': 71.43}, radius 2500 m, collected 2026-10-20T06:09:01+00:00, raw 380, kept 150
* landmarks: centre {'lat': 51.089, 'lon': 71.416}, radius citywide m, collected 2026-10-20T06:09:46+00:00, raw 44, kept 44
* landmarks: centre {'lat': 51.089, 'lon': 71.416}, radius citywide m, collected 2026-10-20T06:40:10+00:00, raw 204, kept 201

## Categories

* cafe: 99
* restaurant: 86
* fast_food: 54
* mall: 50
* artwork: 44
* park: 37
* playground: 25
* worship: 17
* attraction: 16
* sports: 12
* theatre: 9
* museum: 8
* campus: 7
* library: 7
* arts_centre: 6
* stadium: 6
* cinema: 5
* fountain: 4
* ice_cream: 4
* gallery: 2
* theme_park: 2
* other: 1
* zoo: 1

## Names

Display-name source per interface language (see docs/NAMING.md):

* kk: {'original': 419, 'osm': 59}
* ru: {'original': 362, 'osm': 116}
* en: {'original': 383, 'osm': 95}

* English shows the ORIGINAL name (with an English type label): 197 places; of these 6 also get a labelled descriptive translation.
* Records with old unverified names (kept only as search aliases): 13
* Unnamed places with a generated label: 24

### Places without a sourced English name (first 60)

| ID | Original name | Type | Descriptive translation | Pronunciation aid |
|---|---|---|---|---|
| osm:node/12093489321 | Дареджани | restaurant |  | Daredzhani |
| osm:way/1456208624 | Бейбітшілік пен Келісім аллеясы | park |  | Beybitshilik pen Kelisim alleyasy |
| osm:node/12520559591 | Лепим и варим | cafe |  | Lepim i varim |
| osm:node/10211901020 | Тануки | restaurant |  | Tanuki |
| osm:node/6408255389 | завтрак бар | cafe |  | zavtrak Bar |
| osm:node/4908968226 | Казахская национальная академия хореографии | campus |  | Kazakhskaya natsionalnaya akademiya khoreografii |
| osm:node/13681674667 | Лето | cafe |  | Leto |
| osm:node/5878515487 | Жуссан | restaurant |  | Zhussan |
| osm:node/5878572885 | Семейное кафе бум | cafe |  | Semeynoe Cafe Boom |
| osm:node/5878503586 | Қазақ еліне мың алғыс | artwork |  | Qazaq eline myng algys |
| osm:way/1462136136 | Тайқазан | fountain |  | Tayqazan |
| osm:node/12049030101 | ШашлычОк | fast_food |  | ShashlychOk |
| osm:way/419217546 | Қазақстан Республикасының Ұлттық Қорғаныс Университеті | campus |  | Qazaqstan Respublikasynyng Ulttyq Qorganys Universiteti |
| osm:relation/20321069 | Макет ракеты-носителя Зенит | artwork |  | Maket rakety-nositelya Zenit |
| osm:relation/20321070 | Макет ракеты-носителя Протон | artwork |  | Maket rakety-nositelya Proton |
| osm:way/734476104 | Буран | artwork |  | Buran |
| osm:node/13088473063 | "Астана Жұлдызы" Ескерткіші | artwork |  | "Astana Zhuldyzy" Eskertkishi |
| osm:node/2388707906 | Астана-Экспо КС | gallery |  | Astana-EXPO KS |
| osm:node/2671060738 | Избушка | cafe |  | Izbushka |
| osm:node/2671060739 | Дастархан | cafe |  | Dastarkhan |
| osm:node/4953253121 | Саксаул | restaurant |  | Saksaul |
| osm:way/230358854 | Сквер | park |  | Skver |
| osm:node/4506675474 | IMAX Кинопарк7 | cinema |  | IMAX Kinopark7 |
| osm:node/12520559589 | Лепим и варим | cafe |  | Lepim i varim |
| osm:node/4594452990 | йога-центр "натарадж" | sports |  | yoga-Centre "nataradzh" |
| osm:node/3404172551 | Кишлак | restaurant |  | Kishlak |
| osm:node/14087643081 | Жылқылар үйірі | attraction |  | Zhylqylar uyiri |
| osm:node/12959449801 | Культура Диктует | cafe |  | Kultura Diktuet |
| osm:node/4133836392 | Дастаркан | cafe |  | Dastarkan |
| osm:node/13340040665 | Жетігенші | artwork |  | Zhetigenshi |
| osm:node/13340040666 | Қобызшы | artwork |  | Qobyzshy |
| osm:way/1470780026 | Дубовая аллея | park |  | Dubovaya Alley |
| osm:way/258753491 | Әнші субұрқақтар | fountain |  | Anshi suburqaqtar |
| osm:node/5936655589 | Мост | restaurant |  | Most |
| osm:node/11443113045 | ЧебурекМи | fast_food |  | CheburekMi |
| osm:node/5593300634 | Чир Chic | restaurant |  | Chir Chic |
| osm:way/734514013 | Сызықтық саябақ | park |  | Syzyqtyq sayabaq |
| osm:node/4915119663 | Арай | restaurant |  | Aray |
| osm:node/5244250150 | Рахат | restaurant |  | Rakhat |
| osm:node/11345949808 | Синяя волна | fast_food |  | Sinyaya volna |
| osm:node/4108293490 | Тайказан | cafe |  | Taykazan |
| osm:node/12049030095 | ШашлычОк | fast_food |  | ShashlychOk |
| osm:node/13333409377 | Махтумкули Фраги | artwork |  | Makhtumkuli Fragi |
| osm:node/13760723564 | Чайхана | cafe |  | Chaykhana |
| osm:node/12917116702 | Рыба пила | restaurant |  | Ryba pila |
| osm:node/13340050452 | Хатико | artwork |  | Khatiko |
| osm:node/12179661909 | Шашлычок | fast_food |  | Shashlychok |
| osm:way/499328449 | Астана балет | theatre |  | Astana balet |
| osm:way/1449322337 | НЛО | attraction |  | NLO |
| osm:way/1449322338 | Ұшатын автобус | attraction |  | Ushatyn avtobus |
| osm:way/1449322339 | Динопарк | attraction |  | Dinopark |
| osm:way/1449322340 | Электронды көліктер | attraction |  | Elektrondy kolikter |
| osm:way/1449322329 | Конвой | attraction |  | Konvoy |
| osm:way/1449317691 | Лепим и варим | cafe |  | Lepim i varim |
| osm:way/240909210 | Сарыарқа | mall |  | Saryarqa |
| osm:way/1449301389 | Намазхана | worship |  | Namazkhana |
| osm:way/240909219 | Алаша | restaurant |  | Alasha |
| osm:node/5764228295 | Тифлисъ | restaurant |  | Tiflis |
| osm:node/4913160607 | Меруерт | restaurant |  | Meruert |
| osm:way/158630906 | Тамсан | cafe |  | Tamsan |

### Legacy names demoted to unverified aliases (first 40)

* osm:relation/20321069 Макет ракеты-носителя Зенит: Макет ракеты-носителя Союз
* osm:node/5936674486 York food: Coffee&food
* osm:way/499328514 Mega Silk Way: Mega SilkWay Astana, Мега Силк Вей
* osm:way/549307755 Мәңгілік Ел салтанат қақпасы: Мәңгілік ел қақпасы
* osm:node/4916060859 М.В. Ломоносов атындағы Мәскеу мемлекеттік университеті Қазақстан филиалы: Қазақстан Республикасының Ауыл шаруашылығы министрлігі, Ministry of Agriculture
* osm:node/5880883095 Hilton Astana: Хилтон Астана
* osm:way/1460537088 Astana Musical: Қазақстан Орталық концерт залы, Центральный концертный зал «Казахстан»
* osm:way/1460700597 Атамекен Қазақстан картасы этно-мемориалдық кешені: Атамекен (мұражай), Atameken miniature park
* osm:way/166265821 Сарыарқа: Republican Cycling Track
* osm:way/762780007 Abu Dhabi Plaza: Абу-Даби Плаза
* osm:way/917478479 Астана Опера: Астана Опера (театр)
* osm:node/4894937300 Қазақстан Республикасының Ұлттық Мұражайы: Қазақстан Республикасының Ұлттық музейі
* osm:way/502046662 «Ататүрік» саябағы: Park Ataturk

To fix a name: add a reviewed entry to data/name_overrides.json (ID, text, source URL, review date).
