import os
import re
import csv

# Point this to your taxonomies folder
base_dir = os.path.join('analyzer', 'reference_taxonomies')

def generate_test_file(schema_filename, output_filename, prefix, target_percentage=8):
    filepath = os.path.join(base_dir, schema_filename)
    
    if not os.path.exists(filepath):
        print(f"⚠️ Error: Could not find {filepath}. Make sure the filename matches what's in your reference_taxonomies folder!")
        return
        
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    # Extract tags (handles both CSV and XML/XSD)
    elements = set()
    if filepath.endswith('.csv'):
        with open(filepath, 'r', encoding='utf-8-sig') as csvfile:
            first_line = csvfile.readline()
            delimiter = ';' if ';' in first_line else ','
            csvfile.seek(0)
            reader = csv.DictReader(csvfile, delimiter=delimiter)
            for row in reader:
                name = row.get('Element Name') or row.get('Concept name') or row.get('Disclosure Code')
                if name: elements.add(name.strip())
    else:
        matches = re.findall(r'<[a-zA-Z0-9_:]*element[^>]*name=["\']([^"\']+)["\']', content, re.IGNORECASE)
        elements = set(match.strip() for match in matches)

    total_tags = len(elements)
    if total_tags == 0:
        print(f"⚠️ No tags found in {schema_filename}!")
        return

    # Calculate exactly 8% of the tags
    tags_needed = max(5, int(total_tags * (target_percentage / 100)))
    selected_tags = list(elements)[:tags_needed]
    
    # Generate the iXBRL HTML content
    html_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns:ix="http://www.xbrl.org/2008/inlineXBRL" xmlns:{prefix}="http://example.com/{prefix}">
    <head><title>Test Report for {prefix.upper()}</title></head>
    <body style="font-family: sans-serif; padding: 40px;">
        <h2>Simulated {prefix.upper()} Report (~{target_percentage}% Compliance)</h2>
        <p>This document contains exactly <strong>{tags_needed} valid tags</strong> out of the {total_tags} expected in the taxonomy.</p>
        <hr/>
"""
    # Write the valid tags
    for tag in selected_tags:
        html_content += f'        <div style="margin-bottom: 5px;"><ix:nonNumeric name="{prefix}:{tag}" contextRef="FY24">Valid simulated data for {tag}</ix:nonNumeric></div>\n'
        
    # Inject fake tags to trigger the Yellow "Unrecognized" Accordion and a small penalty
    html_content += f"""
        <hr/>
        <h3 style="color: darkorange;">Custom / Unrecognized Extensions</h3>
        <div><ix:nonNumeric name="{prefix}:CustomFakeTagOne" contextRef="FY24">Fake Data 1</ix:nonNumeric></div>
        <div><ix:nonNumeric name="{prefix}:CustomFakeTagTwo" contextRef="FY24">Fake Data 2</ix:nonNumeric></div>
    </body>
</html>"""

    with open(output_filename, 'w', encoding='utf-8') as f:
        f.write(html_content)
        
    print(f"✅ Success! Created '{output_filename}'")
    print(f"   -> It contains {tags_needed} valid tags (~{target_percentage}%) and 2 custom tags.")

# --- RUN THE GENERATOR FOR YOUR FRAMEWORKS ---

# 1. SASB Test File
generate_test_file('sasb.xml', 'SASB_8_Percent_Test.xhtml', 'sasb', target_percentage=8)

# 2. IFRS S1 Test File (Change the .xsd name to exactly match what is in your folder)
generate_test_file('ifrs_s1_schema.xsd', 'IFRS_S1_8_Percent_Test.xhtml', 'ifrs-s1', target_percentage=8)

# 3. US GAAP Test File (Change the .xsd name to exactly match what is in your folder)
generate_test_file('us_gaap_schema.xsd', 'US_GAAP_8_Percent_Test.xhtml', 'us-gaap', target_percentage=8)