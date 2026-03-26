import os
import csv
import re

def load_reference_taxonomy(standard, custom_file_path=None):
    """Safely loads taxonomy from either CSV or XML/XSD Schema files."""
    elements = set()
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 1. Custom File Override
    if custom_file_path and os.path.exists(custom_file_path):
        filepath = custom_file_path
        print(f"✅ ENGINE: Using Custom Taxonomy Upload: {filepath}")
    else:
        # 2. Strict Mapping (No silent fallbacks to GRI!)
        filename_map = {
            'GRI': 'gri_schema.xsd',              
            'IFRS S1': 'ifrs_s1_schema.xsd',      
            'IFRS S2': 'ifrs_s2_schema.xsd',      
            'IFRS Accounting': 'ifrs_18_schema.xsd',
            'SASB': 'sasb.xml',
            'ESRS': 'esrs_schema.xsd',
            'US GAAP': 'us_gaap_schema.xsd'
        }
        
        filename = filename_map.get(standard)
        if not filename:
            print(f"❌ ENGINE ERROR: Unknown standard selected '{standard}'. Check your HTML dropdown values.")
            return elements

        # Check inside the reference folder, then fallback to base folder
        filepath = os.path.join(base_dir, 'reference_taxonomies', filename)
        if not os.path.exists(filepath): 
            filepath = os.path.join(base_dir, filename)

    if not os.path.exists(filepath):
        print(f"❌ ENGINE ERROR: The required schema file '{filename}' is MISSING from your folder!")
        return elements

    print(f"✅ ENGINE: Successfully loaded Rulebook -> {filepath}")

    ext = os.path.splitext(filepath)[1].lower()

    # --- PARSE CSV FILES ---
    if ext == '.csv':
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            first_line = f.readline()
            delimiter = ';' if ';' in first_line else ','
            f.seek(0)
            
            reader = csv.DictReader(f, delimiter=delimiter)
            for row in reader:
                element_name = row.get('Element Name') or row.get('Concept name') or row.get('Disclosure Code')
                if element_name:
                    elements.add(element_name.strip())

    # --- PARSE XML / XSD FILES ---
    elif ext in ['.xml', '.xsd']:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            
            # Extract 'name' attribute from <xsd:element> or <xs:element>
            matches = re.findall(r'<[a-zA-Z0-9_:]*element[^>]*name=["\']([^"\']+)["\']', content, re.IGNORECASE)
            for match in matches:
                elements.add(match.strip())
                
    return elements

def parse_user_xbrl(file_path):
    """Uses raw Regex to extract tags from user's iXBRL or standard XML XBRL document."""
    reported_elements = set()
    
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
        
    # 1. Extract from Inline XBRL (iXBRL / HTML formats)
    # E.g. <ix:nonNumeric name="sasb:WorkforceSafety" ...>
    ix_matches = re.findall(r'<ix:[a-zA-Z0-9_]+[^>]*name=["\'](?:[^:"\']+?:)?([^"\']+)["\']', content, re.IGNORECASE)
    for match in ix_matches:
        reported_elements.add(match.strip())
        
    # 2. Extract from Standard XBRL (Strict XML formats)
    # E.g. <sasb:WorkforceSafety contextRef="...">
    xml_matches = re.findall(r'<[a-zA-Z0-9_]+:([a-zA-Z0-9_]+)[^>]*contextRef=', content, re.IGNORECASE)
    for match in xml_matches:
        reported_elements.add(match.strip())
            
    return reported_elements


def run_xbrl_comparison(comparison_instance):
    """Strict comparison that penalizes gaps and extra tags."""
    
    expected_elements = load_reference_taxonomy(
        comparison_instance.reference_standard, 
        comparison_instance.custom_reference.path if comparison_instance.custom_reference else None
    )
    
    reported_elements = parse_user_xbrl(comparison_instance.user_document.path)
    
    # 1. Mathematical Breakdown
    missing_elements = expected_elements - reported_elements
    extra_elements = reported_elements - expected_elements
    matched_elements = expected_elements.intersection(reported_elements)
    
    total_expected = len(expected_elements)
    
    # 2. Strict Scoring Logic
    if total_expected == 0:
        score = 0 
    else:
        base_score = (len(matched_elements) / total_expected) * 100
        penalty = len(extra_elements) * 2 
        score = max(0, int(base_score - penalty))
    
    # 3. Save Results
    results = {
        "summary": {
            "total_expected": total_expected,
            "total_reported": len(reported_elements),
            "matched_count": len(matched_elements),
            "missing_count": len(missing_elements),
            "unrecognized_count": len(extra_elements)
        },
        "matched": sorted(list(matched_elements)),
        "missing": sorted(list(missing_elements))[:200], 
        "unrecognized": sorted(list(extra_elements))
    }
    
    comparison_instance.results_data = results
    comparison_instance.compliance_score = score
    comparison_instance.is_processed = True
    comparison_instance.save()
    
    return comparison_instance