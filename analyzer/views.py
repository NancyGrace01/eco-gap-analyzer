from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from .models import *
from .forms import *
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
import datetime
import csv
from datetime import timedelta
from django.utils import timezone
from django.template.loader import render_to_string, get_template
from weasyprint import HTML
import weasyprint
from django.core.files.base import ContentFile
from .xbrl_engine import run_xbrl_comparison
import json
import requests
from django.http import JsonResponse
import openai
from django.views.decorators.csrf import csrf_exempt
import PyPDF2
from .ai_engine import *
from django.conf import settings
from openai import OpenAI
import re
import os
from django.urls import reverse
from django.contrib import messages
from xhtml2pdf import pisa
from django.utils.text import slugify
import concurrent.futures


def register(request):
    next_url = request.GET.get('next', '')
    
    # Check if this user was invited
    invite_company_id = request.session.get('invite_company_id')
    invite_company = Company.objects.get(id=invite_company_id) if invite_company_id else None

    if request.method == 'POST':
        form = CustomRegistrationForm(request.POST)
        
        # If they were invited, they don't need to submit new company data
        if invite_company:
            form.fields['company_name'].required = False
            form.fields['sector'].required = False
            form.fields['industries'].required = False  # NEW: Make industries optional for invited guests

        if form.is_valid():
            user = form.save()
            
            if invite_company:
                # Link them to the existing company
                company = invite_company
                
                # Mark the invite as used
                token = request.session.get('invite_token')
                if token:
                    TeamInvitation.objects.filter(token=token).update(is_accepted=True)
                
                # Clear the session
                del request.session['invite_company_id']
                del request.session['invite_token']
            else:
                # Create a brand new company
                company_name = form.cleaned_data.get('company_name')
                sector = form.cleaned_data.get('sector')
                industries = form.cleaned_data.get('industries')  # NEW: Extract the list of industries
                
                # NEW: Pass industries into the defaults when creating the company
                company, _ = Company.objects.get_or_create(
                    name=company_name, 
                    defaults={
                        'sector': sector,
                        'industries': industries
                    }
                )
            
            UserProfile.objects.create(user=user, company=company)
            login(request, user)
            
            return redirect(request.POST.get('next') or 'dashboard')
    else:
        form = CustomRegistrationForm()
        
        # Pre-fill and lock the fields if they are an invited guest
        if invite_company:
            form.fields['company_name'].initial = invite_company.name
            form.fields['company_name'].widget.attrs['readonly'] = True
            
            form.fields['sector'].initial = invite_company.sector
            form.fields['sector'].widget.attrs['readonly'] = True
            form.fields['sector'].widget.attrs['style'] = 'pointer-events: none;'
            
            # NEW: Pre-fill and lock the industries field for invited guests
            form.fields['industries'].initial = invite_company.industries
            form.fields['industries'].widget.attrs['readonly'] = True
            form.fields['industries'].widget.attrs['style'] = 'pointer-events: none;'

    return render(request, 'registration/register.html', {'form': form, 'next': next_url, 'invite_company': invite_company})

def home(request):
    """Renders the public landing page."""
    # If the user is already logged in, you could redirect them straight to the dashboard
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    return render(request, 'analyzer/home.html')


@login_required
def dashboard(request):
    # Claim orphaned AI reports from the guest session
    if 'guest_ai_report_id' in request.session:
        AnalysisReport.objects.filter(id=request.session['guest_ai_report_id'], user__isnull=True).update(user=request.user)
        del request.session['guest_ai_report_id']
        
    # Claim orphaned XBRL jobs from the guest session
    if 'guest_xbrl_job_id' in request.session:
        XBRLComparison.objects.filter(id=request.session['guest_xbrl_job_id'], user__isnull=True).update(user=request.user)
        del request.session['guest_xbrl_job_id']
        
    # Fetch user's historical data (Top 5 for the tables)
    ai_reports = AnalysisReport.objects.filter(user=request.user).order_by('-created_at')[:5]
    xbrl_jobs = XBRLComparison.objects.filter(user=request.user).order_by('-created_at')[:5]
    
    # Calculate True Total Scans (un-sliced)
    total_ai_count = AnalysisReport.objects.filter(user=request.user).count()
    total_xbrl_count = XBRLComparison.objects.filter(user=request.user).count()

    # 1. Calculate the YoY delta (Filter by YoY specific trends)
    yoy_data = [0, 0, 0, 0] 
    latest_yoy = ComparativeReport.objects.filter(
        user=request.user,
        findings__trend__in=['Improved', 'Regressed', 'Unchanged', 'New Gap']
    ).distinct().order_by('-created_at').first()
    
    if latest_yoy:
        for finding in latest_yoy.findings.all():
            if finding.trend == 'Improved': yoy_data[0] += 1
            elif finding.trend == 'Regressed': yoy_data[1] += 1
            elif finding.trend == 'Unchanged': yoy_data[2] += 1
            elif finding.trend == 'New Gap': yoy_data[3] += 1

    # 2. NEW: Calculate the Peer Benchmark delta (Filter by Cross-Company trends)
    peer_data = [0, 0, 0, 0]
    latest_peer = ComparativeReport.objects.filter(
        user=request.user,
        findings__trend__in=['Document 1 Leads', 'Document 2 Leads', 'Parity', 'Mutual Gap']
    ).distinct().order_by('-created_at').first()
    
    if latest_peer:
        for finding in latest_peer.findings.all():
            if finding.trend == 'Document 1 Leads': peer_data[0] += 1
            elif finding.trend == 'Document 2 Leads': peer_data[1] += 1
            elif finding.trend == 'Parity': peer_data[2] += 1
            elif finding.trend == 'Mutual Gap': peer_data[3] += 1
                
    context = {
        'ai_reports': ai_reports,
        'xbrl_jobs': xbrl_jobs,
        'total_scans': total_ai_count + total_xbrl_count,
        'yoy_data': yoy_data,
        'peer_data': peer_data  # Pass the new data to the chart
    }                
    
    return render(request, 'analyzer/dashboard.html', context)


@login_required
def profile_view(request):
    user_profile = getattr(request.user, 'profile', None)
    company = user_profile.company if user_profile else None
    
    # Fetch all team members in the same company
    team_members = []
    if company:
        team_members = UserProfile.objects.filter(company=company).select_related('user')
        
    context = {
        'company': company,
        'team_members': team_members,
    }
    return render(request, 'registration/profile.html', context)


@login_required
def edit_profile(request):
    user_profile = getattr(request.user, 'profile', None)
    company = user_profile.company if user_profile else None
    
    if not company:
        messages.error(request, "No workspace found to edit.")
        return redirect('profile')

    if request.method == 'POST':
        form = CompanyProfileForm(request.POST, instance=company)
        if form.is_valid():
            form.save()
            messages.success(request, "Workspace profile updated successfully!")
            return redirect('profile')
    else:
        # Pre-fill the form with the current company data
        form = CompanyProfileForm(instance=company)
        # Ensure the JSON list maps correctly to the checkboxes
        if company.industries:
            form.initial['industries'] = company.industries

    return render(request, 'registration/edit_profile.html', {'form': form, 'company': company})



def upload_document(request):
    if request.method == 'POST':
        uploaded_file = request.FILES.get('document')
        if not uploaded_file:
            return redirect('home')

        # 1. Create the Report Instance
        report = AnalysisReport.objects.create(
            user=request.user if request.user.is_authenticated else None,
            document=uploaded_file
        )
        
        if not request.user.is_authenticated:
            request.session['guest_ai_report_id'] = str(report.id)

        # 2. Get User Sector (For tailored Risk Analysis)
        user_sector = "General"
        if request.user.is_authenticated and hasattr(request.user, 'profile') and request.user.profile.company:
            user_sector = request.user.profile.company.sector

        # 3. Extract Text WITH EVIDENCE MAPPING (Page Numbers)
        document_text = ""
        try:
            reader = PyPDF2.PdfReader(uploaded_file)
            for i, page in enumerate(reader.pages):
                text = page.extract_text()
                if text:
                    document_text += f"\n\n--- PAGE {i+1} ---\n{text}"
        except Exception as e:
            print(f"PDF Extraction Error: {e}")
            return render(request, 'analyzer/upload.html', {'error': 'Failed to read the PDF file.'})

        # To control API costs, limit the text length slightly if it's massive
        masked_text = document_text[:35000]

        # 4. Process The Client's 3 Proprietary Frameworks
        frameworks = ['GRI', 'IFRS S1', 'IFRS S2']
        
        # Define the exact Layer Names the client requested 
        # (Updated to "Contextual Analysis" to fix the sidebar)
        layer_mapping = {
            "keywords_analysis": "Keywords Analysis",
            "thematic_analysis": "Contextual Analysis", 
            "quality_maturity": "Disclosure Quality & Maturity",
            "compliance_gap": "Gap Analysis (Conformance & Compliance)",
            "gap_prioritization": "Gap Prioritization",
            "risk_analysis": "Risk Analysis"
        }
        
        ai_results_map = {}

        # =======================================================================
        # NEW PARALLEL PROCESSING LOGIC: Run all frameworks simultaneously
        # =======================================================================
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            future_to_std = {
                executor.submit(analyze_document, masked_text, std, company_sector=user_sector): std 
                for std in frameworks
            }
            for future in concurrent.futures.as_completed(future_to_std):
                std = future_to_std[future]
                try:
                    ai_results_map[std] = future.result()
                except Exception as exc:
                    print(f"⚠️ API call generated an exception for {std}: {exc}")
                    ai_results_map[std] = None

        # Once all parallel calls finish, sequentially save them to the Database
        for standard in frameworks:
            ai_results = ai_results_map.get(standard)
            
            # Failsafe in case OpenAI fails
            if not ai_results:
                print(f"⚠️ API failed for {standard}. Skipping.")
                continue
                
            # --- SAVE ALL 6 LAYERS TO THE DATABASE ---
            for json_key, layer_name in layer_mapping.items():
                
                layer_obj = AnalysisLayer.objects.create(
                    report=report, 
                    standard=standard, 
                    layer_type=layer_name,
                    summary_text=f"Processing complete for {layer_name}."
                )
                
                findings_to_create = []
                
                # Since analyze_document now returns the perfectly formatted arrays for ALL layers 
                # including Keywords Analysis, we just loop through and save them cleanly.
                for f in ai_results.get(json_key, []):
                    findings_to_create.append(LayerFinding(
                        layer=layer_obj, 
                        code=f.get('code', '-'), # Correctly mapping the code
                        item=f.get('item', 'Unknown'), 
                        status=f.get('status', 'Pending'), 
                        details=f.get('details', ''), 
                        recommendation=f.get('recommendation', ''),
                        page_number=f.get('page_number', 'N/A'),
                        section_name=f.get('section_name', 'N/A'),
                        raw_excerpt=f.get('raw_excerpt', 'Excerpt unavailable.'),
                        status_breakdown=f.get('status_breakdown', 'Detailed breakdown unavailable.')
                    ))
                    
                # Bulk save for performance
                LayerFinding.objects.bulk_create(findings_to_create)
                layer_obj.is_processed = True
                layer_obj.save()

        report.is_processed = True
        report.save()

        return redirect('results_preview', report_id=report.id)

    return render(request, 'analyzer/upload.html')


def results_preview(request, report_id):
    if request.user.is_authenticated and 'guest_ai_report_id' in request.session:
        AnalysisReport.objects.filter(id=request.session['guest_ai_report_id'], user__isnull=True).update(user=request.user)
        del request.session['guest_ai_report_id']
        
    report = get_object_or_404(AnalysisReport, id=report_id)
    report.check_and_delete_file()

    delete_time = report.created_at + timedelta(minutes=10)
    now = timezone.now()
    remaining_seconds = max(0, (delete_time - now).total_seconds())

    if not report.is_processed:
        from .utils import run_analysis_pipeline
        run_analysis_pipeline(report)
        report.is_processed = True
        report.save()

    all_layers = report.layers.prefetch_related('findings').all()
    
    charts_data = {}
    for layer in all_layers:
        std_slug = slugify(layer.standard)
        if std_slug not in charts_data:
            charts_data[std_slug] = []
            
        met = partial = unmet = 0
        for f in layer.findings.all():
            status = f.status.lower() if f.status else ""
            if 'unmet' in status: unmet += 1
            elif 'partially' in status: partial += 1
            else: met += 1
            
        charts_data[std_slug].append({
            'layer_id': layer.id,
            'layer_name': layer.layer_type,
            'met': met, 'partial': partial, 'unmet': unmet,
            'total': met + partial + unmet
        })

    standards_data = {
        "GRI": all_layers.filter(standard="GRI"), 
        "IFRS_S1": all_layers.filter(standard="IFRS S1"), 
        "IFRS_S2": all_layers.filter(standard="IFRS S2")  
    }
    
    # ----------------------------------------------------
    # NEW: Check if the user has an active subscription
    # ----------------------------------------------------
    is_premium = False
    if request.user.is_authenticated:
        # Fallback safely in case the DB field hasn't been migrated yet
        is_premium = getattr(request.user.profile, 'has_active_subscription', False)

    context = {
        'report': report,
        'standards_data': standards_data,
        'charts_data_json': json.dumps(charts_data), 
        'remaining_seconds': int(remaining_seconds),
        'is_premium': is_premium # Pass paywall status to template
    }
    return render(request, 'analyzer/results_preview.html', context)


# =========================================================================
# NEW: SUBSCRIPTION & PAYSTACK INTEGRATION VIEWS
# =========================================================================

@login_required
def pricing_page(request):
    """Renders the checkout page with the Paystack integration."""
    # Ensure PAYSTACK_PUBLIC_KEY is in your settings.py!
    public_key = getattr(settings, 'PAYSTACK_PUBLIC_KEY', 'pk_test_f35a6ec0843e23b59ee4a2511519398e90f90389')
    return render(request, 'analyzer/pricing.html', {'paystack_pub_key': public_key})

@login_required
def verify_payment(request):
    """Called via redirect from Paystack popup after successful transaction."""
    reference = request.GET.get('reference')
    if not reference:
        messages.error(request, "Invalid payment reference.")
        return redirect('pricing')

    # Verify the transaction with Paystack Servers
    secret_key = getattr(settings, 'PAYSTACK_SECRET_KEY', 'sk_test_bd691d331b5471619910423603b14581ae6cfe06')
    headers = {"Authorization": f"Bearer {secret_key}"}
    
    try:
        response = requests.get(f"https://api.paystack.co/transaction/verify/{reference}", headers=headers)
        res_data = response.json()

        if res_data.get('status') and res_data['data']['status'] == 'success':
            # Unlock Premium for User
            profile = request.user.profile
            profile.has_active_subscription = True
            profile.save()
            messages.success(request, "Payment successful! You now have full access to Premium Analysis.")
            return redirect('dashboard')
        else:
            messages.error(request, "Payment verification failed. Please try again.")
            return redirect('pricing')
    except Exception as e:
        print(f"Paystack verification error: {e}")
        messages.error(request, "A network error occurred while verifying payment.")
        return redirect('pricing')


def export_layer_pdf(request, layer_id):
    layer = get_object_or_404(AnalysisLayer, id=layer_id)
    
    # Guest Security Check: Ensure only the report owner can download it
    if layer.report.user and layer.report.user != request.user:
        return redirect('upload_document')

    # Prepare data for the PDF
    context = {
        'layer': layer,
        'findings': layer.findings.all(),
        'report': layer.report,
        'generated_date': timezone.now().strftime("%Y-%m-%d %H:%M")
    }
    
    # Render the HTML template into a string
    html_string = render_to_string('analyzer/layer_pdf_report.html', context)
    
    # Convert HTML to PDF using WeasyPrint
    pdf_file = HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf()
    
    response = HttpResponse(pdf_file, content_type='application/pdf')
    
    # Create a dynamic filename (e.g., "GRI_Keyword_Analysis_Report.pdf")
    safe_name = layer.layer_type.replace(" ", "_")
    filename = f"{layer.standard}_{safe_name}_Report.pdf"
    
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


def xbrl_upload(request):
    if request.method == 'POST':
        standard = request.POST.get('standard', 'GRI')
        uploaded_file = request.FILES.get('document')
        pasted_text = request.POST.get('raw_text')
        custom_ref = request.FILES.get('custom_reference')

        # Create the comparison job
        job = XBRLComparison(
            user=request.user if request.user.is_authenticated else None,
            reference_standard=standard
        )
        
        if not request.user.is_authenticated:
            request.session['guest_xbrl_job_id'] = str(job.id)

        # Handle File vs Pasted Text (Client Request)
        if uploaded_file:
            job.user_document = uploaded_file
        elif pasted_text:
            # Convert pasted text into a real file for the engine to read
            job.user_document.save('pasted_xbrl_data.xhtml', ContentFile(pasted_text.encode('utf-8')))
        else:
            return render(request, 'analyzer/xbrl_upload.html', {'error': 'Please upload a file or paste text.'})

        # Handle Custom Taxonomy Upload
        if custom_ref:
            job.custom_reference = custom_ref

        job.save()

        # Run the engine
        run_xbrl_comparison(job)

        return redirect('xbrl_result', job_id=job.id)

    return render(request, 'analyzer/xbrl_upload.html')

def xbrl_result(request, job_id):
    job = get_object_or_404(XBRLComparison, id=job_id)
    
    # Security: Only owner can view
    if job.user and job.user != request.user:
        return redirect('xbrl_upload')

    # NEW: Check subscription status
    is_premium = False
    if request.user.is_authenticated:
        is_premium = getattr(request.user.profile, 'has_active_subscription', False)

    context = {
        'job': job,
        'summary': job.results_data.get('summary', {}),
        'missing': job.results_data.get('missing', []),
        'matched': job.results_data.get('matched', []),
        'unrecognized': job.results_data.get('unrecognized', []),
        'is_premium': is_premium  # Pass the premium flag to the template!
    }
    return render(request, 'analyzer/xbrl_result.html', context)



def xbrl_export_csv(request, job_id):
    job = get_object_or_404(XBRLComparison, id=job_id)
    
    # Security: Ensure only the owner can download it
    if job.user and job.user != request.user:
        return redirect('xbrl_upload')

    # Create the HTTP response with CSV headers
    response = HttpResponse(content_type='text/csv')
    
    # Dynamic filename based on the standard and job ID
    safe_standard = job.reference_standard.replace(" ", "_")
    filename = f"XBRL_Gap_Report_{safe_standard}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    
    # 1. Write the Header & Score
    writer.writerow(['ECO GAP ANALYZER - XBRL DIAGNOSTIC REPORT'])
    writer.writerow(['Reference Standard', job.reference_standard])
    writer.writerow(['Taxonomy Compliance Score', f"{job.compliance_score}%"])
    writer.writerow([]) # Blank row for spacing
    
    # 2. Write Summary Statistics
    summary = job.results_data.get('summary', {})
    writer.writerow(['--- SUMMARY STATISTICS ---'])
    writer.writerow(['Total Expected Tags', summary.get('total_expected', 0)])
    writer.writerow(['Total Reported Tags', summary.get('total_reported', 0)])
    writer.writerow(['Matched Compliant Tags', summary.get('matched_count', 0)])
    writer.writerow(['Missing Required Tags', summary.get('missing_count', 0)])
    writer.writerow(['Unrecognized Custom Tags', summary.get('unrecognized_count', 0)])
    writer.writerow([])
    
    # 3. Write Missing Tags (The critical gaps)
    writer.writerow(['--- MISSING REQUIRED ELEMENTS (ACTION NEEDED) ---'])
    writer.writerow(['Tag Name'])
    for tag in job.results_data.get('missing', []):
        writer.writerow([tag])
    writer.writerow([])
    
    # 4. Write Unrecognized Tags
    writer.writerow(['--- UNRECOGNIZED / CUSTOM TAGS ---'])
    writer.writerow(['Tag Name'])
    for tag in job.results_data.get('unrecognized', []):
        writer.writerow([tag])
    writer.writerow([])
    
    # 5. Write Matched Tags
    writer.writerow(['--- MATCHED COMPLIANT TAGS ---'])
    writer.writerow(['Tag Name'])
    for tag in job.results_data.get('matched', []):
        writer.writerow([tag])

    return response



def xbrl_export_pdf(request, job_id):
    """Generates a professional PDF report for XBRL diagnostic results."""
    job = get_object_or_404(XBRLComparison, id=job_id)
    
    # Security: Ensure only the owner can view/download
    if job.user and job.user != request.user:
        return redirect('xbrl_upload')

    # Get the company data safely
    company = None
    if request.user.is_authenticated and hasattr(request.user, 'profile'):
        company = request.user.profile.company

    context = {
        'job': job,
        'summary': job.results_data.get('summary', {}),
        'missing': job.results_data.get('missing', []),
        'matched': job.results_data.get('matched', []),
        'unrecognized': job.results_data.get('unrecognized', []),
        'company': company,
        'generated_date': timezone.now().strftime("%B %d, %Y")
    }
    
    # Render the HTML template
    template = get_template('analyzer/xbrl_pdf_report.html')
    html = template.render(context)
    
    # Create the HTTP response with PDF headers
    response = HttpResponse(content_type='application/pdf')
    
    # Dynamic Filename
    company_name = company.name if company else "Guest"
    safe_company_name = "".join([c if c.isalnum() else "_" for c in company_name])
    safe_standard = job.reference_standard.replace(" ", "_")
    filename = f"{safe_company_name}_{safe_standard}_XBRL_Audit.pdf"
    
    # Use 'inline' to preview in the browser instead of forced download
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    
    # Convert HTML to PDF
    pisa_status = pisa.CreatePDF(html, dest=response)
    
    if pisa_status.err:
        return HttpResponse(f'We had some errors generating your PDF <pre>{html}</pre>')
        
    return response


@login_required
def invite_team_member(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        company = request.user.profile.company
        
        # Create a unique invite token in the database
        invite = TeamInvitation.objects.create(company=company, email=email)
        
        # Generate the registration link
        invite_link = request.build_absolute_uri(reverse('accept_invite', args=[invite.token]))
        
        # For now, we will just display the link on the dashboard so you can test it easily!
        # (Later, we can wire this up to an actual SMTP email sender)
        messages.success(request, f"Invite generated! Send this link to {email}: {invite_link}")
        
    return redirect('dashboard')

def accept_invite(request, token):
    # Verify the token is valid and hasn't been used
    invite = get_object_or_404(TeamInvitation, token=token, is_accepted=False)
    
    # Save the company ID to their browser session so the register page knows who they are
    request.session['invite_company_id'] = invite.company.id
    request.session['invite_token'] = str(invite.token)
    
    messages.info(request, f"You have been invited to join {invite.company.name}. Please create your account.")
    return redirect('register')



@csrf_exempt 
def chatbot_api(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            user_message = data.get('message', '')
            
            if not user_message:
                return JsonResponse({'error': 'Message is required'}, status=400)

            system_prompt = """
            You are 'EcoAssist', the official AI assistant for the Eco Gap Analyzer platform. 
            You are an expert in Sustainability & Financial Reporting (GRI, IFRS S1/S2, ESRS, SASB, US GAAP, and IFRS Accounting), AND a technical guide for this software.
            You can help users with:
            1. Understanding sustainability and financial frameworks, as well as their specific reporting requirements.
            2. Using the PDF AI Gap Analysis tool.
            3. Understanding XBRL/iXBRL digital tagging, taxonomies, and the XBRL Validator tool.
            4. Navigating the platform (e.g., explaining how to export PDF/CSV reports).
            Your tone is professional, concise, and highly helpful. Keep answers under 3 paragraphs.
            """

            # CHANGED: Corrected OpenAI initialization
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.3 # Low temperature for accurate, professional answers
            )
            
            ai_response = response.choices[0].message.content
            return JsonResponse({'reply': ai_response})
            
        except Exception as e:
            # Fallback message if OpenAI quota is exceeded or API fails
            print(f"Chatbot Error: {e}")  # Check your terminal for this exact message!
            return JsonResponse({
                'reply': "I am currently experiencing high network traffic. Please try asking your question again in a moment, or check the platform's standard documentation."
            })

    return JsonResponse({'error': 'Invalid request method'}, status=405)



def extract_raw_text_for_comparison(filepath):
    """Helper function to safely extract text for the delta engine"""
    text = ""
    try:
        reader = PyPDF2.PdfReader(filepath)
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted: text += extracted + "\n"
    except Exception as e:
        print(f"Error reading PDF for comparison: {e}")
    return text

def compare_reports(request):
    if request.method == 'POST':
        compare_type = request.POST.get('compare_type', 'yoy') # Distinguishes the two form tabs
        
        # 1. Handle Base Report (Upload vs Existing)
        base_report = None
        if 'base_report_file' in request.FILES:
            base_report = AnalysisReport.objects.create(
                user=request.user if request.user.is_authenticated else None,
                document=request.FILES['base_report_file']
            )
        else:
            base_id = request.POST.get('base_report')
            if base_id:
                base_report = AnalysisReport.objects.get(id=base_id)

        # 2. Handle New Report (Upload vs Existing)
        new_report = None
        if 'new_report_file' in request.FILES:
            new_report = AnalysisReport.objects.create(
                user=request.user if request.user.is_authenticated else None,
                document=request.FILES['new_report_file']
            )
        else:
            new_id = request.POST.get('new_report')
            if new_id:
                new_report = AnalysisReport.objects.get(id=new_id)

        # Validate we have both documents
        if not base_report or not new_report:
            messages.error(request, "Please select or upload both documents to compare.")
            return redirect('compare_reports')
            
        if base_report == new_report:
            messages.error(request, "Please select two different documents to compare.")
            return redirect('compare_reports')
        
        # Extract Text (Capped at 25,000 chars each to fit in the prompt window)
        base_text = extract_raw_text_for_comparison(base_report.document.path)[:25000]
        new_text = extract_raw_text_for_comparison(new_report.document.path)[:25000]

        # ==========================================
        # 3. GATEKEEPER CHECK FOR YoY ANALYSIS
        # ==========================================
        if compare_type == 'yoy':
            # Feed the first 4000 chars to AI to verify they are the same company
            is_same_company = verify_same_company(base_text[:4000], new_text[:4000])
            if not is_same_company:
                messages.error(request, "YoY Analysis Failed: The AI detected that these documents belong to different companies. Please use the 'Cross-Company Comparison' tab instead.")
                return redirect('compare_reports')
        
        # ==========================================
        # 4. RUN ANALYSIS PIPELINE
        # ==========================================
        comp_report = ComparativeReport.objects.create(
            user=request.user if request.user.is_authenticated else None,
            base_report=base_report, 
            new_report=new_report
        )
        
        frameworks = ['GRI', 'IFRS S1', 'IFRS S2']
        all_findings = []
        exec_summary_combined = ""
        
        for std in frameworks:
            if compare_type == 'yoy':
                delta_results = analyze_comparative_delta(base_text, new_text, std)
            else:
                delta_results = analyze_cross_comparison(base_text, new_text, std)
            
            if delta_results:
                exec_summary_combined += f"### {std} Summary\n{delta_results.get('executive_summary', '')}\n\n"
                
                for f in delta_results.get('findings', []):
                    all_findings.append(ComparativeFinding(
                        comparative_report=comp_report,
                        framework=std,
                        requirement=f.get('requirement', 'Unknown'),
                        base_status=f.get('base_status', 'Unknown'),
                        new_status=f.get('new_status', 'Unknown'),
                        trend=f.get('trend', 'Unchanged'),
                        ai_analysis=f.get('ai_analysis', '')
                    ))
                    
        # Save everything and redirect
        comp_report.executive_summary = exec_summary_combined
        comp_report.save()
        ComparativeFinding.objects.bulk_create(all_findings)
        
        # Tag the report so the template knows what kind it is
        request.session[f'comp_type_{comp_report.id}'] = compare_type
        
        return redirect('comparative_result', comp_id=comp_report.id)
        
    # GET request: Let them select the reports to compare via the dual-tab UI
    reports = AnalysisReport.objects.filter(user=request.user).order_by('-created_at') if request.user.is_authenticated else []
    return render(request, 'analyzer/select_comparison.html', {'reports': reports})

@login_required
def comparative_result(request, comp_id):
    comp_report = ComparativeReport.objects.get(id=comp_id)
    is_cross_compare = request.session.get(f'comp_type_{comp_report.id}') == 'cross'
    
    # NEW: Check subscription status
    is_premium = False
    if request.user.is_authenticated:
        is_premium = getattr(request.user.profile, 'has_active_subscription', False)
    
    context = {
        'comp_report': comp_report,
        'is_cross_compare': is_cross_compare,
        'is_premium': is_premium  # Pass this to the template!
    }
    return render(request, 'analyzer/comparative_result.html', context)


@login_required
def export_comparative_pdf(request, comp_id):
    comp_report = ComparativeReport.objects.get(id=comp_id)
    is_cross_compare = request.session.get(f'comp_type_{comp_report.id}') == 'cross'
    
    # Render the same template, but as a string
    html_string = render_to_string('analyzer/comparative_result.html', {
        'comp_report': comp_report,
        'is_cross_compare': is_cross_compare
    })
    
    # Convert to PDF
    pdf_file = weasyprint.HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf()
    
    # Create the HTTP response
    response = HttpResponse(pdf_file, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Comparative_Report_{comp_report.id}.pdf"'
    
    return response