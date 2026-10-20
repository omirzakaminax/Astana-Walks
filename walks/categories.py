"""Internal categories, how OSM tags map to them, visit-time ranges, indoor/outdoor.

Visit-time ranges and indoor/outdoor flags are our own planning heuristics (not
source data) and are labelled as approximate wherever they are shown.
"""
from __future__ import annotations

LANGS = ("kk", "ru", "en")

# key: (en, ru, kk, min_visit_min, max_visit_min, indoor)
CATEGORIES: dict[str, tuple[str, str, str, int, int, bool]] = {
    "cafe": ("Cafe", "Кафе", "Кафе", 15, 45, True),
    "restaurant": ("Restaurant", "Ресторан", "Мейрамхана", 30, 75, True),
    "fast_food": ("Fast food", "Фастфуд", "Фастфуд", 10, 30, True),
    "ice_cream": ("Ice cream", "Мороженое", "Балмұздақ", 10, 20, True),
    "park": ("Park", "Парк", "Саябақ", 15, 60, False),
    "playground": ("Playground", "Детская площадка", "Балалар алаңы", 15, 45, False),
    "museum": ("Museum", "Музей", "Мұражай", 40, 120, True),
    "gallery": ("Art gallery", "Галерея", "Галерея", 20, 60, True),
    "attraction": ("Attraction", "Достопримечательность", "Көрікті орын", 10, 45, False),
    "viewpoint": ("Viewpoint", "Смотровая площадка", "Шолу алаңы", 10, 30, False),
    "artwork": ("Public art or monument", "Арт-объект или памятник", "Өнер нысаны немесе ескерткіш", 5, 15, False),
    "fountain": ("Fountain", "Фонтан", "Субұрқақ", 5, 15, False),
    "mall": ("Shopping mall", "Торговый центр", "Сауда орталығы", 30, 90, True),
    "cinema": ("Cinema", "Кинотеатр", "Кинотеатр", 100, 150, True),
    "theatre": ("Theatre or concert hall", "Театр или концертный зал", "Театр немесе концерт залы", 90, 180, True),
    "library": ("Library", "Библиотека", "Кітапхана", 20, 90, True),
    "arts_centre": ("Arts centre", "Арт-центр", "Өнер орталығы", 20, 60, True),
    "sports": ("Sports and fitness", "Спорт и фитнес", "Спорт және фитнес", 45, 90, True),
    "zoo": ("Zoo or aquarium", "Зоопарк или океанариум", "Хайуанаттар бағы немесе океанариум", 60, 150, True),
    "theme_park": ("Amusement park", "Парк развлечений", "Ойын-сауық паркі", 45, 150, False),
    "campus": ("University campus", "Университетский кампус", "Университет кампусы", 10, 30, False),
    "worship": ("Mosque, church or temple", "Мечеть, храм или собор", "Мешіт, шіркеу немесе ғибадатхана", 15, 40, True),
    "stadium": ("Stadium or arena", "Стадион или арена", "Стадион немесе арена", 15, 40, False),
    "other": ("Other place", "Другое место", "Басқа орын", 10, 45, False),
}

# Ordered list of (osm_key, osm_value, category). First match wins.
OSM_TAG_RULES: list[tuple[str, str, str]] = [
    ("tourism", "museum", "museum"),
    ("tourism", "gallery", "gallery"),
    ("tourism", "zoo", "zoo"),
    ("tourism", "aquarium", "zoo"),
    ("tourism", "theme_park", "theme_park"),
    ("tourism", "viewpoint", "viewpoint"),
    ("tourism", "artwork", "artwork"),
    ("tourism", "attraction", "attraction"),
    ("historic", "monument", "artwork"),
    ("historic", "memorial", "artwork"),
    ("amenity", "cafe", "cafe"),
    ("amenity", "restaurant", "restaurant"),
    ("amenity", "fast_food", "fast_food"),
    ("amenity", "ice_cream", "ice_cream"),
    ("amenity", "cinema", "cinema"),
    ("amenity", "theatre", "theatre"),
    ("amenity", "concert_hall", "theatre"),
    ("amenity", "library", "library"),
    ("amenity", "arts_centre", "arts_centre"),
    ("amenity", "fountain", "fountain"),
    ("leisure", "playground", "playground"),
    ("leisure", "park", "park"),
    ("leisure", "garden", "park"),
    ("leisure", "water_park", "theme_park"),
    ("leisure", "amusement_arcade", "theme_park"),
    ("leisure", "sports_centre", "sports"),
    ("leisure", "fitness_centre", "sports"),
    ("shop", "mall", "mall"),
    ("amenity", "university", "campus"),
    ("amenity", "place_of_worship", "worship"),
    ("leisure", "stadium", "stadium"),
]

_LANG_INDEX = {"en": 0, "ru": 1, "kk": 2}


def category_from_tags(tags: dict) -> str:
    for key, value, cat in OSM_TAG_RULES:
        if tags.get(key) == value:
            return cat
    if "historic" in tags:
        return "artwork"
    return "other"


def label(category: str, lang: str = "en") -> str:
    row = CATEGORIES.get(category, CATEGORIES["other"])
    return row[_LANG_INDEX.get(lang, 0)]


def visit_range(category: str) -> tuple[int, int]:
    row = CATEGORIES.get(category, CATEGORIES["other"])
    return row[3], row[4]


def is_indoor(category: str) -> bool:
    """Category-based heuristic only. Use indoor_basis() to know how certain this is."""
    return CATEGORIES.get(category, CATEGORIES["other"])[5]


def indoor_basis(poi: dict) -> tuple[bool, str]:
    """(indoor?, basis). basis = "osm_tag" when OSM tags say so, else "category" (an estimate)."""
    tags = poi.get("osm_tags") or {}
    if tags.get("indoor") in ("yes", "room", "area", "corridor") or tags.get("location") in ("indoor", "underground"):
        return True, "osm_tag"
    if tags.get("covered") == "yes":
        return True, "osm_tag"
    if tags.get("building") and tags.get("building") not in ("no", "roof"):
        return True, "osm_tag"
    if tags.get("indoor") == "no" or tags.get("location") == "outdoor":
        return False, "osm_tag"
    return is_indoor(poi.get("category", "other")), "category"


def all_labels() -> dict[str, dict[str, str]]:
    return {k: {lang: label(k, lang) for lang in LANGS} for k in CATEGORIES}
