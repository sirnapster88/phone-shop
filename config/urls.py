from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from operators import views as operator_views

urlpatterns = [
    path('', operator_views.index, name='home'),
    path('healthz/', operator_views.healthz, name='healthz'),

    path(
        'login/',
        auth_views.LoginView.as_view(
            template_name='registration/login.html',
            redirect_authenticated_user=True
        ),
        name='login'
    ),

    path('admin/', admin.site.urls),
    path('operators/', include('operators.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
