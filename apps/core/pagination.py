"""
Custom Pagination Classes
"""

from rest_framework.pagination import PageNumberPagination, CursorPagination
from rest_framework.response import Response


class StandardResultsPagination(PageNumberPagination):
    """Standard pagination with configurable page size"""
    
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
    
    def get_paginated_response(self, data):
        return Response({
            'success': True,
            'data': data,
            'pagination': {
                'count': self.page.paginator.count,
                'total_pages': self.page.paginator.num_pages,
                'current_page': self.page.number,
                'page_size': self.get_page_size(self.request),
                'next': self.get_next_link(),
                'previous': self.get_previous_link(),
            }
        })


class LargeResultsPagination(PageNumberPagination):
    """Pagination for large datasets"""
    
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 500
    
    def get_paginated_response(self, data):
        return Response({
            'success': True,
            'data': data,
            'pagination': {
                'count': self.page.paginator.count,
                'total_pages': self.page.paginator.num_pages,
                'current_page': self.page.number,
                'page_size': self.get_page_size(self.request),
                'next': self.get_next_link(),
                'previous': self.get_previous_link(),
            }
        })


class CursorResultsPagination(CursorPagination):
    """Cursor-based pagination for real-time data"""
    
    page_size = 20
    ordering = '-created_at'
    cursor_query_param = 'cursor'
    
    def get_paginated_response(self, data):
        return Response({
            'success': True,
            'data': data,
            'pagination': {
                'next': self.get_next_link(),
                'previous': self.get_previous_link(),
            }
        })
