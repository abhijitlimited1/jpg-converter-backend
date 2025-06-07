from django.urls import path
from django.http import HttpResponse
from . import views

# Simple health check view
def health_check(request):
    return HttpResponse("OK", status=200)

urlpatterns = [
    path('jpg-to-pdf/', views.JpgToPdfView.as_view()),
    path('pdf-to-jpg/', views.PdfToJpgView.as_view()),
    path('health/', health_check, name='health_check'),
]