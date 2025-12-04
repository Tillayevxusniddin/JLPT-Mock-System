from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

API_V1_PREFIX = 'api/v1'

urlpatterns = [
    path('admin/', admin.site.urls),
    path(f'{API_V1_PREFIX}/auth/', include('apps.authentication.urls')),
    path(f'{API_V1_PREFIX}/invitations/', include('apps.invitations.urls')),
    path(f'{API_V1_PREFIX}/organizations/', include('apps.organizations.urls')),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    
    try:
        import debug_toolbar
        urlpatterns += [path('__debug__/', include(debug_toolbar.urls))]
    except ImportError:
        pass