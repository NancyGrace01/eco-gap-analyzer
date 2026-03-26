from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import Company

# Define Sector Choices directly in the form
SECTOR_CHOICES = [
    ('', '-- Select a Sector --'),
    ('Consumer Goods', 'Consumer Goods'),
    ('Extractives & Minerals Processing', 'Extractives & Minerals Processing'),
    ('Financials', 'Financials'),
    ('Food & Beverage', 'Food & Beverage'),
    ('Health Care', 'Health Care'),
    ('Infrastructure', 'Infrastructure'),
    ('Renewable Resources & Alternative Energy', 'Renewable Resources & Alternative Energy'),
    ('Resource Transformation', 'Resource Transformation'),
    ('Services', 'Services'),
    ('Technology & Communications', 'Technology & Communications'),
    ('Transportation', 'Transportation'),
]

# Flat list of all possible industries for backend validation
INDUSTRY_LIST = [
    "Apparel, Accessories & Footwear", "Appliance Manufacturing", "Building Products & Furnishings", "Household & Personal Products", "Multiline & Specialty Retailers & Distributors", "E-Commerce", "Toys & Sporting Goods",
    "Coal Operations", "Construction Materials", "Iron & Steel Producers", "Metals & Mining", "Oil & Gas – Exploration & Production", "Oil & Gas – Midstream", "Oil & Gas – Refining & Marketing", "Oil & Gas – Services",
    "Asset Management & Custody Activities", "Commercial Banks", "Consumer Finance", "Insurance", "Investment Banking & Brokerage", "Mortgage Finance", "Security & Commodity Exchanges",
    "Agricultural Products", "Alcoholic Beverages", "Food Retailers & Distributors", "Meat, Poultry & Dairy", "Non-Alcoholic Beverages", "Processed Foods", "Restaurants", "Tobacco",
    "Biotechnology & Pharmaceuticals", "Medical Equipment & Supplies", "Health Care Delivery", "Managed Care",
    "Electric Utilities & Power Generators", "Gas Utilities & Distributors", "Water Utilities & Services", "Renewable Energy", "Engineering & Construction Services", "Waste Management", "Real Estate",
    "Biofuels", "Forestry Management", "Fuel Cells & Industrial Batteries", "Pulp & Paper Products", "Solar Technology & Project Developers", "Wind Technology & Project Developers",
    "Chemicals", "Containers & Packaging", "Electrical & Electronic Equipment", "Industrial Machinery & Goods", "Aerospace & Defense",
    "Advertising & Marketing", "Casinos & Gaming", "Education Services", "Hotels & Lodging", "Leisure Facilities", "Media & Entertainment", "Professional & Commercial Services",
    "Hardware", "Internet Media & Services", "Semiconductors", "Software & IT Services", "Telecommunications Services",
    "Air Freight & Logistics", "Airlines", "Automobiles", "Auto Parts", "Marine Transportation", "Rail Transportation", "Road Transportation"
]
INDUSTRY_CHOICES = [(ind, ind) for ind in sorted(INDUSTRY_LIST)]

class CustomRegistrationForm(UserCreationForm):
    company_name = forms.CharField(max_length=255, required=True)
    sector = forms.ChoiceField(choices=SECTOR_CHOICES, required=True)
    
    industries = forms.MultipleChoiceField(
        choices=INDUSTRY_CHOICES, 
        required=True,
        widget=forms.CheckboxSelectMultiple, # <-- THIS FORCES TRUE HTML CHECKBOXES
        help_text="Select all industries that apply to your operations."
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = UserCreationForm.Meta.fields + ('email',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name == 'sector':
                field.widget.attrs.update({
                    'class': 'form-select bg-dark text-white border-secondary',
                    'onchange': 'updateIndustries()'
                })
            elif field_name == 'industries':
                # WE MUST LEAVE THIS BLANK! 
                # Applying Bootstrap 'form-select' or 'form-control' to checkboxes breaks them.
                # Our HTML CSS block handles the styling for this specific field.
                field.widget.attrs.update({'class': 'custom-checkbox-list'})
            else:
                field.widget.attrs.update({
                    'class': 'form-control bg-dark text-white border-secondary', 
                    'placeholder': field.label
                })
                

class CompanyProfileForm(forms.ModelForm):
    sector = forms.ChoiceField(choices=SECTOR_CHOICES, required=True)
    
    industries = forms.MultipleChoiceField(
        choices=INDUSTRY_CHOICES, 
        required=True,
        widget=forms.CheckboxSelectMultiple,
        help_text="Select all industries that apply to your operations."
    )

    class Meta:
        model = Company
        fields = ['name', 'sector', 'industries']
        labels = {
            'name': 'Company / Workspace Name',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name == 'sector':
                field.widget.attrs.update({
                    'class': 'form-select bg-dark text-white border-secondary',
                    'onchange': 'updateIndustries(false)' # False = user changed it
                })
            elif field_name == 'industries':
                field.widget.attrs.update({'class': 'custom-checkbox-list'})
            else:
                field.widget.attrs.update({
                    'class': 'form-control bg-dark text-white border-secondary', 
                    'placeholder': field.label
                })