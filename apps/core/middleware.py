from django.utils.deprecation import MiddlewareMixin
from apps.core.tenant_utils import set_tenant_schema, set_public_schema

class TenantMiddleware(MiddlewareMixin):
    """
    Request kelganda Userning organizatsiyasiga qarab PostgreSQL schemani o'zgartiradi.
    """

    def process_request(self, request):
        # 1. User login qilganmi va uning organization_id si bormi?
        # Eslatma: User modeli public schemada bo'lgani uchun u doim o'qiladi.
        if request.user.is_authenticated and request.user.organization_id:
            
            # Organization ID UUID bo'lgani uchun hex formatini olamiz
            # Schema name formati: "org_{uuid_hex}"
            org_uuid = request.user.organization_id
            schema_name = f"org_{org_uuid.hex}"
            
            try:
                # Schemani o'zgartiramiz
                set_tenant_schema(schema_name)
                request.tenant_schema = schema_name
            except Exception as e:
                # Agar schema topilmasa yoki xato bo'lsa, public ga tushirib qo'yamiz
                # (Productionda log yozish kerak)
                set_public_schema()
                request.tenant_schema = "public"
        else:
            # Login qilmaganlar uchun public schema
            set_public_schema()
            request.tenant_schema = "public"

        return None