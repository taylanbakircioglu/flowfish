"""
PDF Report Generation Service
Creates beautifully designed PDF reports with Flowfish branding
"""

import io
from datetime import datetime
from typing import Optional, List, Dict, Any
import structlog

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image, HRFlowable
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

logger = structlog.get_logger()


# Flowfish Brand Colors
BRAND_PRIMARY = colors.HexColor('#1890ff')  # Blue
BRAND_SECONDARY = colors.HexColor('#13c2c2')  # Cyan
BRAND_SUCCESS = colors.HexColor('#52c41a')  # Green
BRAND_WARNING = colors.HexColor('#faad14')  # Orange
BRAND_DANGER = colors.HexColor('#f5222d')  # Red
BRAND_DARK = colors.HexColor('#001529')  # Dark blue
BRAND_LIGHT = colors.HexColor('#f0f2f5')  # Light gray


class PDFReportService:
    """Service for generating beautiful PDF reports"""
    
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
    
    def _setup_custom_styles(self):
        """Setup custom paragraph styles"""
        # Title style
        self.styles.add(ParagraphStyle(
            name='FlowfishTitle',
            parent=self.styles['Title'],
            fontSize=28,
            textColor=BRAND_DARK,
            spaceAfter=20,
            alignment=TA_CENTER
        ))
        
        # Subtitle style
        self.styles.add(ParagraphStyle(
            name='FlowfishSubtitle',
            parent=self.styles['Normal'],
            fontSize=14,
            textColor=colors.gray,
            spaceAfter=30,
            alignment=TA_CENTER
        ))
        
        # Section header style
        self.styles.add(ParagraphStyle(
            name='FlowfishSection',
            parent=self.styles['Heading1'],
            fontSize=16,
            textColor=BRAND_PRIMARY,
            spaceBefore=20,
            spaceAfter=10,
            borderWidth=1,
            borderColor=BRAND_PRIMARY,
            borderPadding=5
        ))
        
        # Subsection style
        self.styles.add(ParagraphStyle(
            name='FlowfishSubsection',
            parent=self.styles['Heading2'],
            fontSize=12,
            textColor=BRAND_DARK,
            spaceBefore=15,
            spaceAfter=8
        ))
        
        # Body text
        self.styles.add(ParagraphStyle(
            name='FlowfishBody',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.black,
            spaceAfter=6,
            leading=14
        ))
        
        # Stats value
        self.styles.add(ParagraphStyle(
            name='FlowfishStatValue',
            parent=self.styles['Normal'],
            fontSize=24,
            textColor=BRAND_PRIMARY,
            alignment=TA_CENTER
        ))
        
        # Stats label
        self.styles.add(ParagraphStyle(
            name='FlowfishStatLabel',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.gray,
            alignment=TA_CENTER
        ))
    
    def _create_header(self, title: str, subtitle: str = None) -> List:
        """Create report header with branding"""
        elements = []
        
        # Title
        elements.append(Paragraph(f"🐟 {title}", self.styles['FlowfishTitle']))
        
        # Subtitle
        if subtitle:
            elements.append(Paragraph(subtitle, self.styles['FlowfishSubtitle']))
        
        # Horizontal line
        elements.append(HRFlowable(
            width="100%",
            thickness=2,
            color=BRAND_PRIMARY,
            spaceBefore=10,
            spaceAfter=20
        ))
        
        return elements
    
    def _create_metadata_section(self, metadata: Dict[str, Any]) -> List:
        """Create metadata section"""
        elements = []
        
        elements.append(Paragraph("Report Information", self.styles['FlowfishSection']))
        
        # Metadata table
        data = []
        for key, value in metadata.items():
            data.append([
                Paragraph(f"<b>{key}:</b>", self.styles['FlowfishBody']),
                Paragraph(str(value), self.styles['FlowfishBody'])
            ])
        
        if data:
            table = Table(data, colWidths=[2*inch, 4*inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), BRAND_LIGHT),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 10),
                ('RIGHTPADDING', (0, 0), (-1, -1), 10),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ]))
            elements.append(table)
        
        elements.append(Spacer(1, 20))
        return elements
    
    def _create_stats_section(self, stats: Dict[str, Any]) -> List:
        """Create statistics summary section"""
        elements = []
        
        elements.append(Paragraph("Summary Statistics", self.styles['FlowfishSection']))
        
        # Stats grid (4 columns)
        stat_items = list(stats.items())[:8]  # Max 8 stats
        rows = []
        
        for i in range(0, len(stat_items), 4):
            row_data = []
            for j in range(4):
                if i + j < len(stat_items):
                    label, value = stat_items[i + j]
                    cell = [
                        Paragraph(str(value), self.styles['FlowfishStatValue']),
                        Paragraph(label, self.styles['FlowfishStatLabel'])
                    ]
                    row_data.append(cell)
                else:
                    row_data.append(['', ''])
            rows.append(row_data)
        
        if rows:
            # Flatten cells for table
            table_data = []
            for row in rows:
                value_row = []
                label_row = []
                for cell in row:
                    if isinstance(cell, list) and len(cell) == 2:
                        value_row.append(cell[0])
                        label_row.append(cell[1])
                    else:
                        value_row.append('')
                        label_row.append('')
                table_data.append(value_row)
                table_data.append(label_row)
            
            table = Table(table_data, colWidths=[1.5*inch]*4)
            table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('BACKGROUND', (0, 0), (-1, -1), BRAND_LIGHT),
                ('BOX', (0, 0), (-1, -1), 1, BRAND_PRIMARY),
                ('TOPPADDING', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ]))
            elements.append(table)
        
        elements.append(Spacer(1, 20))
        return elements
    
    def _create_data_table(self, title: str, headers: List[str], data: List[List], 
                           col_widths: List[float] = None) -> List:
        """Create a styled data table"""
        elements = []
        
        elements.append(Paragraph(title, self.styles['FlowfishSubsection']))
        
        if not data:
            elements.append(Paragraph("No data available", self.styles['FlowfishBody']))
            return elements
        
        # Prepare table data with headers
        table_data = [headers] + data[:50]  # Limit to 50 rows
        
        # Default column widths
        if not col_widths:
            col_widths = [1.2*inch] * len(headers)
        
        table = Table(table_data, colWidths=col_widths)
        table.setStyle(TableStyle([
            # Header style
            ('BACKGROUND', (0, 0), (-1, 0), BRAND_PRIMARY),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            
            # Data rows - alternating colors
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, BRAND_LIGHT]),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
            
            # Grid
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        
        elements.append(table)
        
        if len(data) > 50:
            elements.append(Paragraph(
                f"<i>Showing 50 of {len(data)} records</i>",
                self.styles['FlowfishBody']
            ))
        
        elements.append(Spacer(1, 15))
        return elements
    
    def _create_footer(self) -> List:
        """Create report footer"""
        elements = []
        
        elements.append(Spacer(1, 30))
        elements.append(HRFlowable(
            width="100%",
            thickness=1,
            color=colors.lightgrey,
            spaceBefore=10,
            spaceAfter=10
        ))
        
        footer_text = f"Generated by Flowfish • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} • Confidential"
        elements.append(Paragraph(footer_text, ParagraphStyle(
            name='Footer',
            fontSize=8,
            textColor=colors.gray,
            alignment=TA_CENTER
        )))
        
        return elements
    
    async def generate_dependency_report(
        self,
        cluster_name: str,
        analysis_name: str,
        nodes: List[Dict],
        edges: List[Dict],
        stats: Dict[str, Any] = None
    ) -> bytes:
        """Generate dependency/graph report PDF"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=50,
            leftMargin=50,
            topMargin=50,
            bottomMargin=50
        )
        
        elements = []
        
        # Header
        elements.extend(self._create_header(
            "Dependency Report",
            f"Service Communication Map for {cluster_name}"
        ))
        
        # Metadata
        elements.extend(self._create_metadata_section({
            "Cluster": cluster_name,
            "Analysis": analysis_name,
            "Generated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "Total Services": len(nodes),
            "Total Connections": len(edges)
        }))
        
        # Stats
        if stats:
            elements.extend(self._create_stats_section(stats))
        
        # Services table
        if nodes:
            service_data = []
            for node in nodes[:30]:
                service_data.append([
                    node.get('name', 'Unknown'),
                    node.get('namespace', '-'),
                    node.get('type', 'service'),
                    str(node.get('connections', 0))
                ])
            
            elements.extend(self._create_data_table(
                "Discovered Services",
                ['Service Name', 'Namespace', 'Type', 'Connections'],
                service_data,
                [2*inch, 1.5*inch, 1*inch, 1*inch]
            ))
        
        # Connections table
        if edges:
            conn_data = []
            for edge in edges[:30]:
                conn_data.append([
                    edge.get('source', 'Unknown'),
                    edge.get('target', 'Unknown'),
                    edge.get('protocol', 'TCP'),
                    str(edge.get('port', '-')),
                    str(edge.get('request_count', 0))
                ])
            
            elements.extend(self._create_data_table(
                "Communication Flows",
                ['Source', 'Destination', 'Protocol', 'Port', 'Requests'],
                conn_data,
                [1.5*inch, 1.5*inch, 0.8*inch, 0.6*inch, 0.8*inch]
            ))
        
        # Footer
        elements.extend(self._create_footer())
        
        doc.build(elements)
        buffer.seek(0)
        return buffer.getvalue()
    
    async def generate_events_report(
        self,
        cluster_name: str,
        analysis_name: str,
        events: List[Dict],
        event_counts: Dict[str, int] = None
    ) -> bytes:
        """Generate events report PDF"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            rightMargin=30,
            leftMargin=30,
            topMargin=40,
            bottomMargin=40
        )
        
        elements = []
        
        # Header
        elements.extend(self._create_header(
            "Events Report",
            f"eBPF Event Analysis for {cluster_name}"
        ))
        
        # Metadata
        elements.extend(self._create_metadata_section({
            "Cluster": cluster_name,
            "Analysis": analysis_name,
            "Generated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "Total Events": len(events)
        }))
        
        # Event counts stats
        if event_counts:
            elements.extend(self._create_stats_section(event_counts))
        
        # Events table
        if events:
            event_data = []
            for event in events[:100]:
                event_data.append([
                    event.get('timestamp', '-')[:19] if event.get('timestamp') else '-',
                    event.get('event_type', 'unknown'),
                    event.get('namespace', '-'),
                    event.get('pod', '-'),
                    str(event.get('details', '-'))[:50]
                ])
            
            elements.extend(self._create_data_table(
                "Event Log",
                ['Timestamp', 'Type', 'Namespace', 'Pod', 'Details'],
                event_data,
                [1.5*inch, 1*inch, 1.2*inch, 1.5*inch, 2.5*inch]
            ))
        
        # Footer
        elements.extend(self._create_footer())
        
        doc.build(elements)
        buffer.seek(0)
        return buffer.getvalue()
    
    async def generate_network_report(
        self,
        cluster_name: str,
        analysis_name: str,
        flows: List[Dict],
        stats: Dict[str, Any] = None
    ) -> bytes:
        """Generate network flows report PDF"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            rightMargin=30,
            leftMargin=30,
            topMargin=40,
            bottomMargin=40
        )
        
        elements = []
        
        # Header
        elements.extend(self._create_header(
            "Network Flows Report",
            f"Network Traffic Analysis for {cluster_name}"
        ))
        
        # Metadata
        elements.extend(self._create_metadata_section({
            "Cluster": cluster_name,
            "Analysis": analysis_name,
            "Generated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "Total Flows": len(flows)
        }))
        
        # Stats
        if stats:
            elements.extend(self._create_stats_section(stats))
        
        # Flows table
        if flows:
            flow_data = []
            for flow in flows[:100]:
                flow_data.append([
                    flow.get('source_pod', '-'),
                    flow.get('dest_pod', '-'),
                    flow.get('dest_ip', '-'),
                    str(flow.get('dest_port', '-')),
                    flow.get('protocol', 'TCP'),
                    str(flow.get('bytes', 0))
                ])
            
            elements.extend(self._create_data_table(
                "Network Flows",
                ['Source', 'Destination', 'Dest IP', 'Port', 'Protocol', 'Bytes'],
                flow_data,
                [1.5*inch, 1.5*inch, 1.2*inch, 0.7*inch, 0.7*inch, 0.8*inch]
            ))
        
        # Footer
        elements.extend(self._create_footer())
        
        doc.build(elements)
        buffer.seek(0)
        return buffer.getvalue()
    
    async def generate_security_report(
        self,
        cluster_name: str,
        analysis_name: str,
        security_events: List[Dict],
        anomalies: List[Dict] = None
    ) -> bytes:
        """Generate security report PDF"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=50,
            leftMargin=50,
            topMargin=50,
            bottomMargin=50
        )
        
        elements = []
        
        # Header
        elements.extend(self._create_header(
            "Security Report",
            f"Security Analysis for {cluster_name}"
        ))
        
        # Metadata
        elements.extend(self._create_metadata_section({
            "Cluster": cluster_name,
            "Analysis": analysis_name,
            "Generated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "Security Events": len(security_events),
            "Anomalies Detected": len(anomalies) if anomalies else 0
        }))
        
        # Security events table
        if security_events:
            event_data = []
            for event in security_events[:50]:
                event_data.append([
                    event.get('timestamp', '-')[:19] if event.get('timestamp') else '-',
                    event.get('severity', 'medium'),
                    event.get('type', 'unknown'),
                    event.get('namespace', '-'),
                    str(event.get('description', '-'))[:40]
                ])
            
            elements.extend(self._create_data_table(
                "Security Events",
                ['Time', 'Severity', 'Type', 'Namespace', 'Description'],
                event_data,
                [1.3*inch, 0.8*inch, 1*inch, 1*inch, 2*inch]
            ))
        
        # Anomalies table
        if anomalies:
            anomaly_data = []
            for anomaly in anomalies[:30]:
                anomaly_data.append([
                    anomaly.get('detected_at', '-')[:19] if anomaly.get('detected_at') else '-',
                    anomaly.get('type', 'unknown'),
                    anomaly.get('resource', '-'),
                    str(anomaly.get('score', 0)),
                    str(anomaly.get('details', '-'))[:40]
                ])
            
            elements.extend(self._create_data_table(
                "Detected Anomalies",
                ['Detected', 'Type', 'Resource', 'Score', 'Details'],
                anomaly_data,
                [1.3*inch, 1*inch, 1.2*inch, 0.6*inch, 2*inch]
            ))
        
        # Footer
        elements.extend(self._create_footer())
        
        doc.build(elements)
        buffer.seek(0)
        return buffer.getvalue()


# Singleton instance
pdf_service = PDFReportService()
