#apps/authentication/backends.py
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q
import logging

User = get_user_model()
logger = logging.getLogger(__name__)

class TenantAwareBackend(ModelBackend):
    """
    Subdomain-based authentication backend.
    
    Extracts subdomain from request.get_host() and matches to Center.slug
    to determine which center context the user is logging into.
    
    Examples:
        edu1.jlpt.uz → Center(slug='edu1')
        edu2.jlpt.uz → Center(slug='edu2')
        jlpt.uz      → No center (Owner/public login)
    """
    
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)
        
        center_id = None
        if request:
            # NEW: Extract subdomain and find matching center
            center_id = self._get_center_id_from_subdomain(request)
        
        try:
            if center_id:
                # Subdomain login: user must belong to this specific center
                user = User.objects.get(email=username, center_id=center_id)
            else:
                # Main domain login: Owner or users without center
                user = User.objects.get(email=username, center__isnull=True)
            
        except User.DoesNotExist:
            logger.debug(f"User not found: {username}, center_id={center_id}")
            return None
        except User.MultipleObjectsReturned:
            logger.warning(f"Multiple users found for {username}, center_id={center_id}")
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            logger.info(f"✅ Authenticated {user.email} via subdomain (center_id={center_id})")
            return user
        
        return None
    
    def _get_center_id_from_subdomain(self, request):
        """
        Extract subdomain from hostname and return matching Center ID.
        
        Examples:
            edu1.jlpt.uz → Center(slug='edu1').id
            edu2.jlpt.uz → Center(slug='edu2').id
            jlpt.uz      → None (main domain)
            localhost    → None
        
        Returns:
            int or None: Center ID if valid subdomain found, else None
        """
        from apps.centers.models import Center
        
        try:
            # Get hostname and remove port if present
            host = request.get_host().split(':')[0]
            
            # Main domains (no tenant context)
            if host in ['localhost', '127.0.0.1', 'jlpt.uz', 'www.jlpt.uz']:
                logger.debug(f"Main domain detected: {host}, no center context")
                return None
            
            # Extract subdomain
            # edu1.jlpt.uz → ['edu1', 'jlpt', 'uz']
            parts = host.split('.')
            
            if len(parts) < 3:
                # Not a subdomain (e.g., jlpt.uz)
                logger.debug(f"No subdomain in {host}")
                return None
            
            subdomain = parts[0]
            logger.debug(f"Extracted subdomain: {subdomain}")
            
            # Find active Center by slug
            center = Center.objects.filter(
                slug=subdomain,
                deleted_at__isnull=True  # Exclude soft-deleted
            ).values('id', 'is_active').first()
            
            if not center:
                logger.warning(f"No center found for subdomain: {subdomain}")
                return None
            
            # Note: We don't check is_active here because that's validated
            # during login in the serializer. Here we just need the center_id
            # to find the correct user account.
            
            logger.info(f"✅ Matched subdomain '{subdomain}' to center ID {center['id']}")
            return center['id']
            
        except Exception as e:
            logger.error(f"Error extracting subdomain: {e}", exc_info=True)
            return None