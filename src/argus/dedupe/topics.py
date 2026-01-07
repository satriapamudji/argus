"""Topic labeling for news items.

Provides heuristic-based topic classification for news items.
Topics are used for diversity constraints in facts bundle selection.
"""

import re
from enum import Enum
from typing import Optional


class TopicLabel(str, Enum):
    """Topic labels for news items.

    Based on spec section 9 and common market news categories.
    """

    MACRO = "macro"  # Fed, ECB, inflation, GDP, jobs
    EARNINGS = "earnings"  # Company earnings, guidance
    GEOPOLITICS = "geopolitics"  # War, sanctions, trade
    POLICY = "policy"  # Regulation, legislation, taxes
    CREDIT = "credit"  # Credit markets, defaults, spreads
    EQUITIES = "equities"  # Stock movements, sectors
    COMMODITIES = "commodities"  # Oil, gold, metals
    CRYPTO = "crypto"  # Bitcoin, Ethereum, crypto markets
    TECH = "tech"  # Technology sector news
    OTHER = "other"  # Uncategorized


# Keyword patterns for each topic
# Order matters - first match wins
TOPIC_KEYWORDS: dict[TopicLabel, list[str]] = {
    TopicLabel.MACRO: [
        r"\bfed\b",
        r"\bfederal reserve\b",
        r"\bfomc\b",
        r"\bpowell\b",
        r"\becb\b",
        r"\bbank of england\b",
        r"\bbank of japan\b",
        r"\bboj\b",
        r"\binflation\b",
        r"\bcpi\b",
        r"\bpce\b",
        r"\bgdp\b",
        r"\bjobs report\b",
        r"\bunemployment\b",
        r"\bnfp\b",
        r"\bnon-?farm payrolls?\b",
        r"\binterest rate\b",
        r"\brate cut\b",
        r"\brate hike\b",
        r"\bcentral bank\b",
        r"\bmonetary policy\b",
        r"\bism\b",
        r"\bpmi\b",
        r"\btreasury\b",
        r"\byield\b",
    ],
    TopicLabel.EARNINGS: [
        r"\bearnings\b",
        r"\beps\b",
        r"\brevenue\b",
        r"\bbeat\b.*\bestimates?\b",
        r"\bmiss\b.*\bestimates?\b",
        r"\bguidance\b",
        r"\boutlook\b",
        r"\bquarterly results?\b",
        r"\bq[1-4]\s+\d{4}\b",
        r"\breported\b.*\bprofit\b",
        r"\breported\b.*\bloss\b",
    ],
    TopicLabel.GEOPOLITICS: [
        r"\bwar\b",
        r"\binvasion\b",
        r"\bsanctions?\b",
        r"\btariffs?\b",
        r"\btrade war\b",
        r"\bukraine\b",
        r"\brussia\b",
        r"\bchina\b.*\btensions?\b",
        r"\btaiwan\b",
        r"\bmiddle east\b",
        r"\bisrael\b",
        r"\biran\b",
        r"\bnorth korea\b",
        r"\bnato\b",
    ],
    TopicLabel.POLICY: [
        r"\bregulat\w+\b",
        r"\blegislat\w+\b",
        r"\bbill\b.*\bpass\w*\b",
        r"\btax\b",
        r"\bsec\b",
        r"\bantitrust\b",
        r"\bcftc\b",
        r"\bcongress\b",
        r"\bsenate\b",
        r"\bhouse\b.*\brepresentatives\b",
        r"\bexecutive order\b",
    ],
    TopicLabel.CREDIT: [
        r"\bcredit\b",
        r"\bdefault\b",
        r"\bbankrupt\w*\b",
        r"\bspread\b",
        r"\bhigh yield\b",
        r"\bjunk bond\b",
        r"\binvestment grade\b",
        r"\bcds\b",
        r"\bcredit rating\b",
        r"\bdowngrade\b",
        r"\bupgrade\b",
    ],
    TopicLabel.COMMODITIES: [
        r"\boil\b",
        r"\bcrude\b",
        r"\bwti\b",
        r"\bbrent\b",
        r"\bgold\b",
        r"\bsilver\b",
        r"\bcopper\b",
        r"\bcommodit\w+\b",
        r"\bopec\b",
        r"\bnatural gas\b",
    ],
    TopicLabel.CRYPTO: [
        r"\bbitcoin\b",
        r"\bbtc\b",
        r"\bethereum\b",
        r"\beth\b",
        r"\bcrypto\w*\b",
        r"\bblockchain\b",
        r"\bstablecoin\b",
        r"\bdefi\b",
        r"\bnft\b",
    ],
    TopicLabel.TECH: [
        r"\bapple\b",
        r"\bmicrosoft\b",
        r"\bgoogle\b",
        r"\balphabet\b",
        r"\bamazon\b",
        r"\bmeta\b",
        r"\bnvidia\b",
        r"\bai\b",
        r"\bartificial intelligence\b",
        r"\bsemiconductor\b",
        r"\bchip\b",
        r"\btech sector\b",
    ],
    TopicLabel.EQUITIES: [
        r"\bs&p\s*500\b",
        r"\bnasdaq\b",
        r"\bdow\b",
        r"\bstock\b",
        r"\bequit\w+\b",
        r"\bsector\b",
        r"\brally\b",
        r"\bselloff\b",
        r"\bbull\b",
        r"\bbear\b",
        r"\bmarket\b.*\b(up|down|fell|rose)\b",
    ],
}


def label_topic(
    title: str,
    snippet: Optional[str] = None,
    source_name: Optional[str] = None,
) -> TopicLabel:
    """Assign a topic label to a news item using heuristic rules.

    Matches keywords in title and snippet against known patterns.
    First matching topic wins (order defined by TOPIC_KEYWORDS).

    Args:
        title: News item title.
        snippet: Optional news item snippet/summary.
        source_name: Optional source name (unused, for future).

    Returns:
        TopicLabel enum value.
    """
    # Combine title and snippet for matching
    text = title.lower()
    if snippet:
        text += " " + snippet.lower()

    # Check each topic's keywords
    for topic, patterns in TOPIC_KEYWORDS.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return topic

    return TopicLabel.OTHER


def get_topic_priority() -> dict[TopicLabel, int]:
    """Get priority ordering for topics.

    Higher priority topics are preferred in selection when
    diversity constraints force a choice.

    Returns:
        Dict mapping topic to priority (higher = more important).
    """
    return {
        TopicLabel.MACRO: 100,
        TopicLabel.GEOPOLITICS: 90,
        TopicLabel.POLICY: 85,
        TopicLabel.CREDIT: 80,
        TopicLabel.EARNINGS: 75,
        TopicLabel.EQUITIES: 70,
        TopicLabel.COMMODITIES: 60,
        TopicLabel.TECH: 55,
        TopicLabel.CRYPTO: 40,
        TopicLabel.OTHER: 10,
    }
