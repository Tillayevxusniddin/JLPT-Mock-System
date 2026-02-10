# apps/core/pagination.py
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import NotFound, ValidationError
from django.core.paginator import InvalidPage, EmptyPage

class DefaultPagination(PageNumberPagination):

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_page_size(self, request):

        if self.page_size_query_param:
            page_size = request.query_params.get(self.page_size_query_param, self.page_size)

            if page_size and str(page_size).lower() == 'all':
                return None

            try:
                page_size = int(page_size)
                if page_size > 0:
                    return min(page_size, self.max_page_size)
            except (ValueError, TypeError):
                pass

        return self.page_size

    def paginate_queryset(self, queryset, request, view=None):

        page_size = self.get_page_size(request)
        if not page_size:
            return None
        
        paginator = self.django_paginator_class(queryset, page_size)
        page_number = self.get_page_number(request, paginator)

        try:
            self.page = paginator.page(page_number)
        except (InvalidPage, EmptyPage) as e:
            total_pages = paginator.num_pages
            if total_pages == 0:
                msg = "No results found. Page numbers start from 1."
            elif page_number > total_pages:
                msg = f"Invalid page. Page {page_number} does not exist. Available pages: 1-{total_pages}."
            else:
                msg = f"Invalid page. Available pages: 1-{total_pages}."
            raise NotFound(msg)
        if paginator.num_pages > 1 and self.template is not None:
            self.display_page_controls = True

        self.request = request
        return list(self.page)

        
