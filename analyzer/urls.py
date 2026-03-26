from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('register/', views.register, name='register'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    
    path('invite/', views.invite_team_member, name='invite_team_member'),
    path('accept-invite/<uuid:token>/', views.accept_invite, name='accept_invite'),
    
    path('upload_document/', views.upload_document, name='upload_document'),
    path('preview/<uuid:report_id>/', views.results_preview, name='results_preview'),
    path('export-layer-pdf/<int:layer_id>/', views.export_layer_pdf, name='export_layer_pdf'),
    
    path('compare/', views.compare_reports, name='compare_reports'),
    path('compare/result/<int:comp_id>/', views.comparative_result, name='comparative_result'),
    path('export-comparative-pdf/<int:comp_id>/', views.export_comparative_pdf, name='export_comparative_pdf'),
    
    path('xbrl-compare/', views.xbrl_upload, name='xbrl_upload'),
    path('xbrl-result/<uuid:job_id>/', views.xbrl_result, name='xbrl_result'),
    path('xbrl-export-csv/<uuid:job_id>/', views.xbrl_export_csv, name='xbrl_export_csv'),
    path('xbrl/export/pdf/<uuid:job_id>/', views.xbrl_export_pdf, name='xbrl_export_pdf'),
    
    path('pricing/', views.pricing_page, name='pricing'),
    path('verify-payment/', views.verify_payment, name='verify_payment'),
    
    path('chat-api/', views.chatbot_api, name='chatbot_api'),
    
]