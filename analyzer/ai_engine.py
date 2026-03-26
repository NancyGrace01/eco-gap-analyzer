import os
import csv
import re
import json
from openai import OpenAI
from django.conf import settings

def load_client_taxonomy(standard):
    """Loads Disclosure Codes and Requirements from proprietary CSVs."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    filename_map = {
        'GRI': 'Project_Gap Assessment Analysis_2.xlsx - GRI.csv',
        'IFRS S1': 'Project_Gap Assessment Analysis_2.xlsx - IFRS S1.csv',
        'IFRS S2': 'Project_Gap Assessment Analysis_2.xlsx - IFRS S2.csv'
    }
    filename = filename_map.get(standard, 'Project_Gap Assessment Analysis_2.xlsx - GRI.csv')
    filepath = os.path.join(base_dir, 'reference_taxonomies', filename)
    
    disclosures = []
    if not os.path.exists(filepath):
        print(f"⚠️ SYSTEM ERROR: AI Keyword file not found at {filepath}")
        return disclosures

    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            actual_headers = {h.strip().replace('\ufeff', ''): h for h in reader.fieldnames} if reader.fieldnames else {}
            
            code_key = next((orig for clean, orig in actual_headers.items() if 'Disclosure Code' in clean), None)
            req_key = next((orig for clean, orig in actual_headers.items() if 'Requirement' in clean), None)
            kw_key = next((orig for clean, orig in actual_headers.items() if 'Keywords' in clean), None)
            name_key = next((orig for clean, orig in actual_headers.items() if 'Disclosure Name' in clean), None)
            tests_key = next((orig for clean, orig in actual_headers.items() if 'Elements (Compliance Tests)' in clean), None)
            
            for row in reader:
                if not code_key: continue
                code = row.get(code_key, '').strip()
                if code:
                    disclosures.append({
                        'code': code, 
                        'disclosure_name': row.get(name_key, '').strip() if name_key else 'General Disclosure',
                        'requirement': row.get(req_key, '').strip() if req_key else 'N/A',
                        'compliance_tests': row.get(tests_key, '').strip() if tests_key else '',
                        'keywords': row.get(kw_key, '').strip() if kw_key else ''
                    })
    except Exception as e:
        print(f"⚠️ CSV READ ERROR: {e}")
        
    return disclosures

def load_extra_taxonomy(filename):
    """Helper to load Context, Maturity, and Risk sheets without breaking core taxonomy."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    filepath = os.path.join(base_dir, 'reference_taxonomies', filename)
    data = []
    if not os.path.exists(filepath): return data
    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                clean_row = {str(k).strip().replace('\ufeff', ''): str(v).strip() for k, v in row.items() if k}
                data.append(clean_row)
    except Exception:
        pass
    return data

def load_risk_taxonomy(standard):
    """Loads universal risk categories, completely bypassing sector constraints."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    # Try the universal project file naming convention first
    filepath = os.path.join(base_dir, 'reference_taxonomies', 'Project_Gap Assessment Analysis_2.xlsx - Risk Analysis.csv')
    
    # Fallback to the generic naming convention if the main file isn't found
    if not os.path.exists(filepath):
        filepath = os.path.join(base_dir, 'reference_taxonomies', f'Risk_Profile_{standard}_General.csv')
        
    data = []
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    keys = list(row.keys())
                    # Dynamically find columns
                    cat_key = next((k for k in keys if k and ('category' in k.lower() or 'risk' in k.lower() or 'name' in k.lower())), keys[0] if keys else None)
                    kw_key = next((k for k in keys if k and ('element' in k.lower() or 'keyword' in k.lower())), None)
                    code_key = next((k for k in keys if k and ('code' in k.lower())), None)
                    
                    if cat_key and row.get(cat_key):
                        data.append({
                            'code': row.get(code_key, '-').strip() if code_key else '-',
                            'category': row.get(cat_key, '').strip(),
                            'elements': row.get(kw_key, '').strip() if kw_key else ''
                        })
        except Exception as e:
            print(f"⚠️ Risk CSV READ ERROR: {e}")
    return data

def analyze_document(text, standard, company_sector="General", company_industries=None):
    """Executes the full 6-Layer Enterprise Workflow."""
    
    disclosures = load_client_taxonomy(standard)
    taxonomy_map = {d['code']: {'name': d.get('disclosure_name', 'General Disclosure'), 'req': d.get('requirement', '')} for d in disclosures}
    
    if disclosures:
        # Removed slicing to ensure AI sees all requirements accurately
        kw_menu = "\n".join([f"[{d['code']}] REQ: {d['requirement']}" for d in disclosures])
    else:
        kw_menu = f"Identify requirements relevant to {standard}."

    context_tax = load_extra_taxonomy('Project_Gap Assessment Analysis_2.xlsx - Context Analysis.csv')
    ctx_menu = "\n".join([f"Step {d.get('Step', '')}: {d.get('Core Activities', '')}" for d in context_tax if d.get('Step')])

    # Load universal risk profile, bypassing sector filtering
    risk_tax = load_risk_taxonomy(standard)
    if risk_tax:
        risk_menu = "\n".join([f"[{r['code']}] {r['category']}" for r in risk_tax])
    else:
        risk_menu = "Identify and evaluate all generic applicable risk categories."

    system_prompt = f"""
    You are an elite Enterprise Sustainability Auditor evaluating a document against the {standard} framework.
    Sector: {company_sector}.

    CRITICAL MANDATE: You MUST perform a substantive analysis for ALL 6 layers. 

    --- LAYER 2 & 3: Keywords & Contextual Analysis ---
    Evaluate these exact requirements:
    {kw_menu}

    --- LAYER 4: Disclosure Quality ---
    Evaluate the report against the 8 Reporting Principles: Accuracy, Balance, Clarity, Comparability, Completeness, Sustainability context, Timeliness, Verifiability.

    STRICT OUTPUT FORMAT RULES FOR LAYERS 2, 3, 4:
    1. DO NOT use phrases like "automated failure" or "automated scan" anywhere in your output. Use "Not disclosed" or "No evidence found" instead.
    2. The 'status_breakdown' field MUST be formatted as a pipe-separated (|) list per line.
       - For Keywords/Contextual: "Keyword Name|Frequency (number)|Presence (1 or 0)|Evidence Snippet"
       - For Disclosure Quality: "Principle Name|Score (0-2)|Presence (1 or 0)|Evidence Snippet"
    3. SCORING FORMULA (CRITICAL RULE): 
       - Coverage = Sum of all Presence values.
       - Coverage % = Coverage / Total number of elements evaluated.
       - If Coverage == 0 -> "Unmet"
       - If Coverage == 1 -> "Partially Met" (Absolute Rule: 1 presence is always Partially Met).
       - If Coverage >= 2 AND Coverage % >= 0.80 -> "Met"
       - If Coverage >= 2 AND Coverage % < 0.80 -> "Partially Met"
    4. SPEED AND EFFICIENCY: Keep all 'details' and 'recommendation' fields to exactly one short sentence (under 15 words).

    --- LAYER 5: GAP PRIORITIZATION ---
    Definitions:
    1. Data Gap: Area where report performs well but data isn't captured or metrics are completely missing.
    2. Disclosure Gap: Data/policies exist but aren't fully or publicly reported to the standard's level of detail.
    (Do NOT use Performance Gaps).
    Format: 
    - 'code' = Standard Code. 
    - 'item' = Disclosure Name. 
    - 'status' = "Unmet" or "Partially Met" (ONLY include these). 
    - 'section_name' = Gap Classification (Data Gap or Disclosure Gap). 
    - 'details' = Context. 
    - 'recommendation' = Comprehensive recommendation. 
    - 'status_breakdown' = "Requirement Item|Evidence Mapping" (use pipe separator, list multiple items on new lines).

    --- LAYER 6: RISK ANALYSIS ---
    Evaluate the report against ALL of the following Risk Categories (Do NOT filter by sector or industry. Evaluate EVERY item):
    {risk_menu}
    Format the 'status_breakdown' strictly as: "Element Name|Frequency (number)|Presence (1 or 0)|Evidence Snippet"

    Return ONLY a valid JSON object matching this exact schema:
    {{
        "keywords_analysis": [
            {{ "metric": "GRI 2-1", "item": "Organization details", "status": "Unmet", "details": "No explicit evidence found.", "recommendation": "Action.", "status_breakdown": "legal name|0|0|Not found", "page_number": "-", "section_name": "-", "raw_excerpt": "-" }}
        ],
        "thematic_analysis": [
            {{ "metric": "GRI 2-1", "item": "Governance Context", "status": "Partially Met", "details": "Context.", "recommendation": "Action.", "status_breakdown": "oversight structure|1|1|Page 5", "page_number": "5", "section_name": "Risk", "raw_excerpt": "Quote" }}
        ],
        "quality_maturity": [
            {{ "metric": "-", "item": "Accuracy", "status": "Met", "details": "Highly accurate.", "recommendation": "Maintain.", "status_breakdown": "Accuracy|2|1|Verified on page 6", "page_number": "6", "section_name": "-", "raw_excerpt": "-" }}
        ],
        "compliance_gap": [
            {{ "metric": "-", "item": "Keywords Analysis", "status": "Met", "details": "Sum of requirements", "recommendation": "-", "status_breakdown": "total: 75", "page_number": "75", "section_name": "93", "raw_excerpt": "-" }}
        ],
        "gap_prioritization": [
            {{ "metric": "GRI 305-1", "item": "Scope 1 emissions", "status": "Unmet", "section_name": "Disclosure Gap", "details": "The report fails to publicly report Scope 1 data.", "recommendation": "Publish internal records.", "status_breakdown": "direct GHG emissions|No public data found\\nstationary combustion|Not disclosed", "page_number": "-", "raw_excerpt": "-" }}
        ],
        "risk_analysis": [
            {{ "metric": "RISK-1", "item": "Credit Risk", "status": "Unmet", "details": "No data.", "recommendation": "Action.", "status_breakdown": "default probability|0|0|Not found", "page_number": "-", "section_name": "Risk Analysis", "raw_excerpt": "-" }}
        ]
    }}
    """

    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o-mini", # <--- HUGE SPEED BOOST: Switched to Mini model
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Analyze this text:\n\n{text[:35000]}"} 
            ],
            temperature=0.0, 
            seed=42
        )
        
        raw_content = response.choices[0].message.content.strip()
        if raw_content.startswith("```json"):
            raw_content = raw_content[7:-3].strip()
        elif raw_content.startswith("```"):
            raw_content = raw_content[3:-3].strip()
            
        parsed_json = json.loads(raw_content)

        text_lower = text.lower()

        # ====================================================================
        # 1. Keywords Analysis (Automated Verification)
        # ====================================================================
        kw_total_freq = 0
        kw_total_presence = 0
        kw_total_elements = 0
        
        llm_kw = {item.get('code', item.get('metric', '')).upper(): item for item in parsed_json.get('keywords_analysis', [])}
        full_kw_layer = []
        
        for tax in disclosures:
            code = tax['code'].upper()
            kws = [k.strip() for k in tax['keywords'].split(',') if k.strip()]
            llm_insight = llm_kw.get(code, {})
            
            bdown = []
            total_presence = 0
            total_freq_for_row = 0
            
            for kw in kws:
                occurrences = len(re.findall(r'\b' + re.escape(kw.lower()) + r'\b', text_lower))
                presence = 1 if occurrences > 0 else 0
                
                total_presence += presence
                total_freq_for_row += occurrences
                bdown.append(f"{kw}|{occurrences}|{presence}")
            
            kw_total_elements += len(kws)
            kw_total_presence += total_presence
            kw_total_freq += total_freq_for_row
                
            cov_pct = total_presence / len(kws) if len(kws) > 0 else 0
            if total_presence == 0: status = 'Unmet'
            elif total_presence == 1: status = 'Partially Met'
            elif cov_pct >= 0.8: status = 'Met'
            else: status = 'Partially Met'
                
            full_kw_layer.append({
                'code': tax['code'],
                'section_name': tax.get('disclosure_name', 'General Disclosure'),
                'item': tax.get('requirement', 'N/A'),
                'status': status,
                'details': llm_insight.get('details', 'Requirement not explicitly addressed in the document.'),
                'recommendation': llm_insight.get('recommendation', 'Ensure all required elements are disclosed in future reports.'),
                'status_breakdown': "\n".join(bdown),
                'page_number': llm_insight.get('page_number', '-'),
                'raw_excerpt': llm_insight.get('raw_excerpt', '-')
            })
            
        parsed_json['keywords_analysis'] = full_kw_layer
        
        kw_cov_pct = (kw_total_presence / kw_total_elements * 100) if kw_total_elements > 0 else 0
        if kw_total_presence == 0: kw_status = 'Unmet'
        elif kw_total_presence == 1: kw_status = 'Partially Met'
        elif kw_cov_pct >= 80: kw_status = 'Met'
        else: kw_status = 'Partially Met'

        # ====================================================================
        # 2. Contextual Analysis (LLM Backed, CSV Forced)
        # ====================================================================
        ctx_total_freq = 0
        ctx_total_presence = 0
        ctx_total_elements = 0
        
        ctx_data_list = parsed_json.get('thematic_analysis', parsed_json.get('contextual_analysis', []))
        llm_ctx = {item.get('code', item.get('metric', '')).upper(): item for item in ctx_data_list}
        
        full_ctx_layer = []
        for tax in disclosures:
            code = tax['code'].upper()
            kws = [k.strip() for k in tax['keywords'].split(',') if k.strip()]
            llm_insight = llm_ctx.get(code, {})
            
            llm_bdown_raw = llm_insight.get('status_breakdown', '')
            llm_kw_map = {}
            for line in llm_bdown_raw.split('\n'):
                parts = line.split('|')
                if len(parts) >= 3:
                    llm_kw_map[parts[0].strip().lower()] = parts
            
            bdown = []
            total_presence = 0
            total_freq_for_row = 0
            
            for kw in kws:
                kw_lower = kw.lower()
                if kw_lower in llm_kw_map:
                    freq = int(llm_kw_map[kw_lower][1]) if llm_kw_map[kw_lower][1].isdigit() else 0
                    presence = int(llm_kw_map[kw_lower][2]) if llm_kw_map[kw_lower][2].isdigit() else 0
                else:
                    occurrences = len(re.findall(r'\b' + re.escape(kw_lower) + r'\b', text_lower))
                    freq = occurrences
                    presence = 1 if occurrences > 0 else 0
                    
                total_presence += presence
                total_freq_for_row += freq
                bdown.append(f"{kw}|{freq}|{presence}")
                
            ctx_total_elements += len(kws)
            ctx_total_presence += total_presence
            ctx_total_freq += total_freq_for_row
                
            cov_pct = total_presence / len(kws) if len(kws) > 0 else 0
            if total_presence == 0: status = 'Unmet'
            elif total_presence == 1: status = 'Partially Met'
            elif cov_pct >= 0.8: status = 'Met'
            else: status = 'Partially Met'
                
            full_ctx_layer.append({
                'code': tax['code'],
                'section_name': tax.get('disclosure_name', 'General Disclosure'),
                'item': tax.get('requirement', 'N/A'),
                'status': status,
                'details': llm_insight.get('details', 'Evaluated for contextual usage but evidence was limited.'),
                'recommendation': llm_insight.get('recommendation', 'Incorporate elements into reporting context.'),
                'status_breakdown': "\n".join(bdown),
                'page_number': llm_insight.get('page_number', '-'),
                'raw_excerpt': llm_insight.get('raw_excerpt', '-')
            })
            
        parsed_json['thematic_analysis'] = full_ctx_layer
        
        ctx_cov_pct = (ctx_total_presence / ctx_total_elements * 100) if ctx_total_elements > 0 else 0
        if ctx_total_presence == 0: ctx_status = 'Unmet'
        elif ctx_total_presence == 1: ctx_status = 'Partially Met'
        elif ctx_cov_pct >= 80: ctx_status = 'Met'
        else: ctx_status = 'Partially Met'

        # ====================================================================
        # 3. Disclosure Quality & Maturity (8 Principles)
        # ====================================================================
        quality_principles = ["Accuracy", "Balance", "Clarity", "Comparability", "Completeness", "Sustainability context", "Timeliness", "Verifiability"]
        llm_quality = {item.get('item', '').lower(): item for item in parsed_json.get('quality_maturity', [])}
        full_quality = []
        
        qual_total_presence = 0
        qual_total_elements = 8
        
        for prin in quality_principles:
            merged_item = {
                'code': '-',
                'section_name': '-',
                'item': prin,
                'status': 'Unmet',
                'details': 'Principle not explicitly addressed in text.',
                'recommendation': f'Align disclosure with {prin} principle.',
                'page_number': '-',
                'raw_excerpt': '-',
                'status_breakdown': f"{prin}|0|0|No evidence mapping found."
            }
            
            matched_key = next((k for k in llm_quality.keys() if prin.lower() in k), None)
            if matched_key:
                llm_data = llm_quality[matched_key]
                merged_item['details'] = llm_data.get('details', merged_item['details'])
                merged_item['recommendation'] = llm_data.get('recommendation', merged_item['recommendation'])
                merged_item['page_number'] = llm_data.get('page_number', '-')
                merged_item['raw_excerpt'] = llm_data.get('raw_excerpt', '-')
                merged_item['status'] = llm_data.get('status', 'Unmet')
                
                raw_bdown = llm_data.get('status_breakdown', '')
                if '|' in raw_bdown:
                    merged_item['status_breakdown'] = raw_bdown
                    parts = raw_bdown.split('|')
                    if len(parts) >= 3:
                        qual_total_presence += int(parts[2]) if parts[2].isdigit() else 0
                else:
                    presence = 1 if 'Met' in merged_item['status'] else 0
                    score = 2 if merged_item['status'] == 'Met' else (1 if presence else 0)
                    merged_item['status_breakdown'] = f"{prin}|{score}|{presence}|{merged_item['raw_excerpt']}"
                    qual_total_presence += presence
                    
            full_quality.append(merged_item)
            
        parsed_json['quality_maturity'] = full_quality
        
        qual_cov_pct = (qual_total_presence / qual_total_elements * 100) if qual_total_elements > 0 else 0
        if qual_total_presence == 0: qual_status = 'Unmet'
        elif qual_total_presence == 1: qual_status = 'Partially Met'
        elif qual_cov_pct >= 80: qual_status = 'Met'
        else: qual_status = 'Partially Met'

        # ====================================================================
        # 4. Gap Analysis (Computed Mathematically)
        # ====================================================================
        # Scaling quality to 80 point scale for visual parity
        scaled_qual_score = int((qual_total_presence / qual_total_elements) * 80) if qual_total_elements > 0 else 0
        
        kw_gap_status = "Unmet" if kw_total_freq <= 25 else ("Partially Met" if kw_total_freq <= 50 else "Met")
        ctx_gap_status = "Unmet" if ctx_total_freq <= 25 else ("Partially Met" if ctx_total_freq <= 50 else "Met")
        qual_gap_status = "Unmet" if scaled_qual_score <= 25 else ("Partially Met" if scaled_qual_score <= 50 else "Met")

        parsed_json['compliance_gap'] = [
            {
                "code": "-",
                "section_name": str(round(kw_cov_pct, 1)), # Pct of Total Score
                "item": "Keyword Analysis",
                "status": kw_gap_status,
                "details": "Sum of requirements",
                "recommendation": "-",
                "status_breakdown": "-",
                "page_number": str(kw_total_freq), # Total Score / Frequency
                "raw_excerpt": "-"
            },
            {
                "code": "-",
                "section_name": str(round(ctx_cov_pct, 1)),
                "item": "Contextual Analysis",
                "status": ctx_gap_status,
                "details": "Sum of requirements",
                "recommendation": "-",
                "status_breakdown": "-",
                "page_number": str(ctx_total_freq),
                "raw_excerpt": "-"
            },
            {
                "code": "-",
                "section_name": str(round(qual_cov_pct, 1)),
                "item": "Disclosure Quality & Maturity",
                "status": qual_gap_status,
                "details": "Sum of requirements",
                "recommendation": "-",
                "status_breakdown": "-",
                "page_number": str(scaled_qual_score),
                "raw_excerpt": "-"
            }
        ]

        # ====================================================================
        # 5. Gap Prioritization (Strict Filtering & Sorting)
        # ====================================================================
        llm_gaps = {item.get('code', item.get('metric', '')).upper(): item for item in parsed_json.get('gap_prioritization', [])}
        full_gap_layer = []

        # Iterate through the calculated Contextual scores to absolutely guarantee no gaps are missed
        for tax, ctx_item in zip(disclosures, full_ctx_layer):
            status = ctx_item['status']
            
            # Only record Unmet and Partially Met results
            if status in ['Unmet', 'Partially Met']:
                code = tax['code'].upper()
                llm_insight = llm_gaps.get(code, {})
                
                # Intelligent Fallback Classification
                raw_class = llm_insight.get('section_name', '')
                if 'Data' in raw_class:
                    classification = 'Data Gap'
                elif 'Disclosure' in raw_class:
                    classification = 'Disclosure Gap'
                else:
                    # Smart Math Fallback: Unmet = No Data. Partially Met = Some Data (Disclosure Gap)
                    classification = 'Data Gap' if status == 'Unmet' else 'Disclosure Gap'
                
                # Dynamic Context & Recommendation based on Classification
                if classification == 'Data Gap':
                    default_details = "Data for this requirement appears to be completely uncaptured or missing."
                    default_rec = "Establish internal mechanisms to capture and record this data."
                else:
                    default_details = "Data exists but is not fully reported to the framework's required level of detail."
                    default_rec = "Expand public disclosures to fully align with framework requirements."
                    
                full_gap_layer.append({
                    'code': tax['code'],
                    'item': tax.get('disclosure_name', 'General Disclosure'), # User wants Disclosure Name here
                    'status': status,
                    'section_name': classification, # Gap Classification
                    'details': llm_insight.get('details', default_details),
                    'recommendation': llm_insight.get('recommendation', default_rec),
                    'status_breakdown': llm_insight.get('status_breakdown', f"{tax.get('requirement', 'Requirement')}|No public data found"),
                    'page_number': ctx_item.get('page_number', '-'), # Pull page number from contextual analysis for mapping
                    'raw_excerpt': '-'
                })

        # Sort: Unmet first (0), Partially Met second (1)
        full_gap_layer.sort(key=lambda x: 0 if 'Unmet' in x['status'] else 1)
        parsed_json['gap_prioritization'] = full_gap_layer
        
        # ====================================================================
        # 6. Risk Analysis (Strict Filtering & Deterministic Fallback)
        # ====================================================================
        risk_data_list = parsed_json.get('risk_analysis', [])
        llm_risk = {item.get('item', '').upper(): item for item in risk_data_list}
        full_risk_layer = []
        
        if risk_tax:
            for tax in risk_tax:
                cat_name = tax['category']
                elements = [k.strip() for k in tax['elements'].split(',') if k.strip()]
                llm_insight = llm_risk.get(cat_name.upper(), {})
                
                llm_bdown_raw = llm_insight.get('status_breakdown', '')
                llm_kw_map = {}
                for line in llm_bdown_raw.split('\n'):
                    parts = line.split('|')
                    if len(parts) >= 3:
                        llm_kw_map[parts[0].strip().lower()] = parts
                
                bdown = []
                total_presence = 0
                
                for el in elements:
                    el_lower = el.lower()
                    if el_lower in llm_kw_map:
                        freq = int(llm_kw_map[el_lower][1]) if llm_kw_map[el_lower][1].isdigit() else 0
                        presence = int(llm_kw_map[el_lower][2]) if llm_kw_map[el_lower][2].isdigit() else 0
                    else:
                        occurrences = len(re.findall(r'\b' + re.escape(el_lower) + r'\b', text_lower))
                        freq = occurrences
                        presence = 1 if occurrences > 0 else 0
                        
                    total_presence += presence
                    bdown.append(f"{el}|{freq}|{presence}|-")
                    
                cov_pct = total_presence / len(elements) if len(elements) > 0 else 0
                
                # If no elements are defined, fall back to AI status
                if len(elements) == 0:
                    status = llm_insight.get('status', 'Unmet')
                    if not bdown:
                        bdown = llm_bdown_raw.split('\n') if llm_bdown_raw else [f"{cat_name} Evaluation|0|0|-"]
                else:
                    if total_presence == 0: status = 'Unmet'
                    elif total_presence == 1: status = 'Partially Met'
                    elif cov_pct >= 0.8: status = 'Met'
                    else: status = 'Partially Met'
                    
                full_risk_layer.append({
                    'code': tax['code'],
                    'section_name': 'Risk Analysis',
                    'item': cat_name,
                    'status': status,
                    'details': llm_insight.get('details', 'Risk evaluation based on document elements.'),
                    'recommendation': llm_insight.get('recommendation', 'Address identified risk gaps.'),
                    'status_breakdown': "\n".join(bdown),
                    'page_number': llm_insight.get('page_number', '-'),
                    'raw_excerpt': llm_insight.get('raw_excerpt', '-')
                })
            
            # Sort: Unmet first (0), Partially Met second (1), Met last (2)
            full_risk_layer.sort(key=lambda x: 0 if 'Unmet' in x['status'] else (1 if 'Partially' in x['status'] else 2))    
            parsed_json['risk_analysis'] = full_risk_layer
        else:
            # Generic fallback if no risk CSV exists
            for item in parsed_json.get('risk_analysis', []):
                item['section_name'] = 'Risk Analysis'

        for key in parsed_json:
            for item in parsed_json[key]:
                if 'metric' in item and 'code' not in item:
                    item['code'] = item['metric']
                    
        return parsed_json
    except Exception as e:
        print(f"Error in OpenAI call: {e}")
        return None

# =========================================================================
# HELPER ENGINES
# =========================================================================

def verify_same_company(text1, text2):
    prompt = "Do these two text excerpts belong to the EXACT SAME company? Reply strictly 'YES' or 'NO'."
    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o-mini", # Switched to mini
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": f"D1: {text1[:2000]}\nD2: {text2[:2000]}"}],
            temperature=0.0,
            seed=42
        )
        return 'YES' in response.choices[0].message.content.strip().upper()
    except: return True

def analyze_comparative_delta(base_text, new_text, standard):
    system_prompt = f"Identify YoY changes for {standard}. Trend must be: Improved, Regressed, Unchanged, or New Gap. Return JSON."
    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o-mini", # Switched to mini
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": f"Old: {base_text[:15000]}\nNew: {new_text[:15000]}"}],
            temperature=0.0,
            seed=42
        )
        content = response.choices[0].message.content.strip()
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
        return json.loads(content)
    except: return None

def analyze_cross_comparison(doc1_text, doc2_text, standard):
    system_prompt = f"Benchmark Document 1 against Document 2 for {standard}. Trend must be: Document 1 Leads, Document 2 Leads, Parity, or Mutual Gap. Return JSON."
    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o-mini", # Switched to mini
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": f"D1: {doc1_text[:15000]}\nD2: {doc2_text[:15000]}"}],
            temperature=0.0,
            seed=42
        )
        content = response.choices[0].message.content.strip()
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
        return json.loads(content)
    except: return None