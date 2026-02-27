
import io
import datetime
import pandas as pd
from django.http import HttpResponse
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status

from rest_framework.renderers import JSONRenderer

class BulkImportExportMixin:
    """
    Mixin to add bulk import and export capabilities to ViewSets.
    Requires serializer_class to be set.
    """

    def get_export_serializer_class(self):
        """Return serializer class used for export. Defaults to serializer_class."""
        return self.get_serializer_class()

    def get_import_serializer_class(self):
        """Return serializer class used for import. Defaults to serializer_class."""
        return self.get_serializer_class()

    @action(detail=False, methods=['get'], url_path='template', renderer_classes=[JSONRenderer])
    def template(self, request):
        """Download a template for bulk import."""
        serializer_class = self.get_import_serializer_class()
        serializer = serializer_class()
        
        fields = []
        # Extract fields from serializer
        for name, field in serializer.fields.items():
            if not field.read_only:
                fields.append(name)
        
        # Create empty dataframe with columns
        df = pd.DataFrame(columns=fields)
        
        # Determine format
        fmt = request.query_params.get('export_format', 'csv')
        
        if fmt == 'xlsx':
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
            buffer.seek(0)
            response = HttpResponse(buffer.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            response['Content-Disposition'] = f'attachment; filename="template.xlsx"'
        else:
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="template.csv"'
            df.to_csv(response, index=False)
            
        return response

    @action(detail=False, methods=['get'], url_path='export', renderer_classes=[JSONRenderer])
    def export(self, request):
        """Export data to CSV/Excel."""
        print(f"DEBUG: Export called. Tenant: {dict(request.headers)}")
        queryset = self.filter_queryset(self.get_queryset())
        print(f"DEBUG: Queryset count: {queryset.count()}")
        serializer_class = self.get_export_serializer_class()
        serializer = serializer_class(queryset, many=True)
        
        # If no data, creating DataFrame from serializer.data might be empty list
        data = serializer.data
        if not data:
             # create empty df with headers from serializer
             serializer_inst = serializer_class()
             df = pd.DataFrame(columns=serializer_inst.fields.keys())
        else:
            df = pd.DataFrame(data)
        
        fmt = request.query_params.get('export_format', 'csv')
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"export_{timestamp}"
        
        if fmt == 'xlsx':
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
            buffer.seek(0)
            response = HttpResponse(buffer.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            response['Content-Disposition'] = f'attachment; filename="{filename}.xlsx"'
        else:
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'
            df.to_csv(response, index=False)
            
        return response

    @action(detail=False, methods=['post'], url_path='import', renderer_classes=[JSONRenderer])
    def import_data(self, request):
        """Import data from CSV/Excel."""
        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            if file.name.endswith('.csv'):
                df = pd.read_csv(file)
            elif file.name.endswith(('.xls', '.xlsx')):
                df = pd.read_excel(file)
            else:
                return Response({'error': 'Unsupported file format. Use CSV or Excel.'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': f'Failed to parse file: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
            
        # Replace NaN with None (null)
        df = df.where(pd.notnull(df), None)
        
        records = df.to_dict('records')
        serializer_class = self.get_import_serializer_class()
        success_count = 0
        errors = []
        
        from apps.core.signals import disable_audit_signals
        
        with disable_audit_signals():
            for index, record in enumerate(records):
                # Clean record: filter out None values if they aren't in fields?
                # Actually serializer handles validation.
                
                serializer = serializer_class(data=record)
                if serializer.is_valid():
                    try:
                        serializer.save()
                        success_count += 1
                    except Exception as e:
                        errors.append({'row': index + 1, 'error': str(e)})
                else:
                    # Format errors nicely
                    formatted_errors = {k: v[0] if isinstance(v, list) else str(v) for k, v in serializer.errors.items()}
                    errors.append({'row': index + 1, 'error': formatted_errors})
                
        return Response({
            'success_count': success_count,
            'attempted_count': len(records),
            'errors': errors
        })
