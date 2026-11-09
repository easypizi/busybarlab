"""Static configuration for Ivanity Fair: reader location and feed catalog."""

from __future__ import annotations

LAT = 37.5841
LON = -122.3661
CITY = "Burlingame, CA"
USER_AGENT = "IvanityFair/1.0 (https://github.com/easypizi/busybarlab)"

BAY_COUNTIES = {
    "alameda", "contra costa", "marin", "napa", "san francisco",
    "san mateo", "santa clara", "solano", "sonoma", "santa cruz",
}

# section id -> list of (outlet name, feed url). Every URL was fetched and parsed on 2026-11-08.
FEEDS: dict[str, list[tuple[str, str]]] = {
    "ai_applied": [
        ("OpenAI", "https://openai.com/news/rss.xml"),
        ("Google AI Blog", "https://blog.google/technology/ai/rss/"),
        ("TechCrunch", "https://techcrunch.com/feed/"),
        ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index"),
        ("Hacker News 300+", "https://hnrss.org/newest?points=300"),
        ("Wired", "https://www.wired.com/feed/rss"),
    ],
    "ai_dev": [
        ("Cursor changelog", "https://cursor.com/changelog/rss.xml"),
        ("OpenAI", "https://openai.com/news/rss.xml"),
        ("Hacker News 300+", "https://hnrss.org/newest?points=300"),
        ("The Register", "https://www.theregister.com/headlines.atom"),
    ],
    "space": [
        ("SpaceNews", "https://spacenews.com/feed/"),
        ("NASASpaceflight", "https://www.nasaspaceflight.com/feed/"),
        ("NASA", "https://www.nasa.gov/feed/"),
        ("Space.com", "https://www.space.com/feeds/all"),
    ],
    "f1": [
        ("Autosport", "https://www.autosport.com/rss/f1/news"),
        ("Motorsport.com", "https://www.motorsport.com/rss/f1/news/"),
        ("Formula1.com", "https://www.formula1.com/content/fom-website/en/latest/all.xml"),
    ],
    "gadgets": [
        ("Engadget", "https://www.engadget.com/rss.xml"),
        ("Hackaday", "https://hackaday.com/blog/feed/"),
        ("The Verge", "https://www.theverge.com/rss/index.xml"),
    ],
    "bay_area": [
        ("SF Standard", "https://sfstandard.com/feed/"),
        ("SFGate", "https://www.sfgate.com/rss/feed/Bay-Area-News-429.php"),
        ("NBC Bay Area", "https://www.nbcbayarea.com/news/local/feed/"),
        ("San Mateo Daily Journal", "https://www.smdailyjournal.com/search/?f=rss"),
    ],
    "incidents": [
        ("San Mateo Daily Journal", "https://www.smdailyjournal.com/search/?f=rss"),
        ("NBC Bay Area", "https://www.nbcbayarea.com/news/local/feed/"),
        ("KTVU", "https://www.ktvu.com/rss/category/news"),
        ("CBS San Francisco", "https://www.cbsnews.com/sanfrancisco/latest/rss/main"),
        ("ABC7 News", "https://abc7news.com/feed/"),
        ("SFGate", "https://www.sfgate.com/rss/feed/Bay-Area-News-429.php"),
    ],
    "russia": [
        ("BBC Russian", "https://feeds.bbci.co.uk/russian/rss.xml"),
        ("Meduza", "https://meduza.io/rss/all"),
    ],
    "tech_jobs": [
        ("TechCrunch", "https://techcrunch.com/feed/"),
        ("The Register", "https://www.theregister.com/headlines.atom"),
        ("SF Standard", "https://sfstandard.com/feed/"),
    ],
    "dnd": [
        ("EN World", "https://www.enworld.org/forums/-/index.rss"),
        ("D&D Beyond", "https://www.dndbeyond.com/posts.rss"),
    ],
    "dnb": [("UKF", "https://ukf.com/feed/")],
}

# section id -> (min, max) stories the desk may print
SECTION_LIMITS: dict[str, tuple[int, int]] = {
    "ai_applied": (2, 5),
    "ai_dev": (2, 4),
    "space": (2, 4),
    "f1": (1, 3),
    "gadgets": (1, 3),
    "bay_area": (2, 4),
    "russia": (2, 3),
    "tech_jobs": (1, 3),
    "dnd": (0, 2),
    "dnb": (0, 2),
}

SECTION_TITLES = {
    "ai_applied": "Applied AI",
    "ai_dev": "AI Dev Tools",
    "space": "Space",
    "f1": "Formula 1",
    "gadgets": "Gadgets",
    "bay_area": "Bay Area",
    "russia": "Russia",
    "tech_jobs": "Tech Jobs",
    "dnd": "D&D and Tabletop",
    "dnb": "Drum & Bass",
}
SECTION_ORDER = list(SECTION_TITLES)

# Lower-case place names that mark a story as local. Used to reject out-of-area incidents.
BAY_PLACES = {
    "bay area", "san francisco", "oakland", "berkeley", "alameda", "san jose", "fremont", "hayward", "san leandro",
    "livermore", "pleasanton", "dublin", "walnut creek", "concord", "richmond", "vallejo", "fairfield", "napa",
    "santa rosa", "petaluma", "san rafael", "novato", "sausalito", "mill valley", "daly city", "south san francisco",
    "san bruno", "millbrae", "burlingame", "san mateo", "foster city", "belmont", "san carlos", "redwood city",
    "menlo park", "atherton", "east palo alto", "palo alto", "mountain view", "sunnyvale", "santa clara", "cupertino",
    "los altos", "milpitas", "campbell", "los gatos", "saratoga", "morgan hill", "gilroy", "half moon bay", "pacifica",
    "santa cruz", "east bay", "south bay", "peninsula", "north bay", "marin", "sonoma", "solano", "contra costa",
    "san mateo county", "santa clara county", "alameda county", "fruitvale", "tracy", "antioch", "pittsburg", "union city",
    "newark", "emeryville", "albany", "el cerrito", "pinole", "hercules", "martinez", "brentwood", "oakley", "danville",
    "san ramon", "lafayette", "orinda", "moraga", "piedmont", "san pablo", "benicia", "american canyon", "sebastopol",
    "san anselmo", "fairfax", "larkspur", "tiburon", "belvedere", "colma", "brisbane", "woodside", "portola valley",
    "sfo", "oyster point",
}
