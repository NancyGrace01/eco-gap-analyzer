"""
GLOBAL SUSTAINABILITY KEYWORDS DICTIONARY
Derived from GRI Standards 2021 and IFRS S1/S2 Taxonomies.
Used for Layer 1 (Keyword Analysis) and Layer 2 (Thematic Analysis).
"""

GLOBAL_KEYWORDS = {
    "GRI": {
        "Environmental": [
            "Scope 1 Emissions", "Scope 2 Emissions", "Scope 3 Emissions",
            "Energy Intensity", "Renewable Energy", "Water Withdrawal",
            "Biodiversity", "Waste Diversion", "Hazardous Waste",
            "Circular Economy", "Climate Adaptation"
        ],
        "Social": [
            "Occupational Health", "Safety Incidents", "Diversity and Inclusion",
            "Human Rights", "Child Labor", "Forced Labor",
            "Local Communities", "Customer Privacy", "Data Security"
        ],
        "Governance": [
            "Anti-Corruption", "Board Diversity", "Executive Compensation",
            "Whistleblowing", "Tax Strategy", "Lobbying",
            "Political Contributions", "Risk Management"
        ]
    },
    "IFRS_S1_S2": {
        "Climate Risks": [
            "Physical Risks", "Transition Risks", "Climate Resilience",
            "Scenario Analysis", "1.5°C Scenario", "Net Zero",
            "Carbon Pricing", "Internal Carbon Price"
        ],
        "Financial Impact": [
            "CapEx", "OpEx", "Asset Stranding", "Revenue Exposure",
            "Capital Allocation", "Financial Position"
        ]
    }
}

def get_all_keywords():
    """Returns a flat list of all keywords for scanning."""
    keywords = []
    for category in GLOBAL_KEYWORDS.values():
        for subcat in category.values():
            keywords.extend(subcat)
    return list(set(keywords))


def get_keywords_for_standard(standard_name):
    """Filters keywords based on whether the standard is GRI or IFRS."""
    keywords = []
    
    if "GRI" in standard_name:
        target = GLOBAL_KEYWORDS.get("GRI", {})
    else:
        # IFRS S1 and S2 share the climate/financial keyword pool
        target = GLOBAL_KEYWORDS.get("IFRS_S1_S2", {})
        
    for subcat in target.values():
        keywords.extend(subcat)
        
    return list(set(keywords))