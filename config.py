"""Configuration for the NBFC Intelligence Platform."""
APP_TITLE = "NBFC Intelligence Platform"
PARSED_DATA_FILE = "nbfc_parsed.xlsx"

COLORS = {
    "background": "#050B12", "surface": "#0B1621", "surface_2": "#102333",
    "text": "#F4F8FB", "muted": "#91A6B5", "cyan": "#20E3D2",
    "green": "#27D17F", "amber": "#FFBB55", "red": "#FF647C",
    "blue": "#55A8FF", "purple": "#8D7CFF", "grid": "#1E3545",
}

# These aliases are normalized before matching, so punctuation/capitalisation differences are harmless.
KPI_ALIASES = {
    "AUM": ["loans advances gross", "gross loans advances", "loan book", "aum", "assets under management"],
    "PAT": ["pat", "profit after tax", "profit for the year"],
    "ROA": ["roa", "return on assets", "return on average assets"],
    "ROE": ["roe", "return on equity", "return on average equity"],
    "GNPA": ["gross npa", "gross npa percent", "gnpa", "gnpa percent", "stage 3 percent"],
    "NNPA": ["net npa", "net npa percent", "nnpa", "nnpa percent"],
    "NIM": ["net interest margin", "nim"],
    "CAR": ["car", "capital adequacy ratio", "crar"],
    "NET_WORTH": ["tnw", "tangible net worth", "net worth"],
    "TOTAL_ASSETS": ["total assets"],
    "TOTAL_DEBT": ["total debt", "borrowings"],
}
PEER_METRICS = ["ROA", "ROE", "GNPA", "NNPA", "NIM", "CAR"]
LOWER_IS_BETTER = {"GNPA", "NNPA"}
ASSET_QUALITY_ALIASES = {
    "Stage 1": ["gross stage 1", "stage 1 percent", "stage i percent"],
    "Stage 2": ["gross stage 2", "stage 2 percent", "stage ii percent"],
    "Stage 3": ["gross stage 3", "stage 3 percent", "stage iii percent"],
}
SEGMENT_ICONS = {
    "Vehicle Finance": "🚘", "Educational Loans": "🎓", "Gold Loan": "◈",
    "Housing Finance Companies": "⌂", "Infrastructure Finance Companies": "🏗",
    "Asset Finance Companies": "▣", "Wholesale": "◆", "Lc": "◎",
}
